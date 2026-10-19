import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.features import suggest as suggest_feature
from ..config import get_settings
from ..db import get_db
from ..entitlements import UserBudget, entitlements, require_feature
from ..models import FeedbackEvent, Item, Outfit, OutfitItem, User
from ..ratelimit import limiter
from ..schemas import FeedbackIn, OutfitOut, SuggestIn, SuggestOut, WeatherOut
from ..security import current_user
from ..serialize import outfit_out
from ..weather import get_weather

router = APIRouter(prefix="/outfits", tags=["outfits"])


def _items_by_id(user: User) -> dict[str, Item]:
    return {str(i.id): i for i in user.items}


@router.post("/suggest", response_model=SuggestOut)
@limiter.limit(lambda: get_settings().suggest_limit)
def suggest(
    request: Request,
    body: SuggestIn,
    idempotency_key: str | None = Header(default=None, max_length=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ent = entitlements(user, db)
    require_feature(ent, "suggest")
    items = list(user.items)
    if not suggest_feature.wardrobe_ready(items):
        raise HTTPException(400, detail={"code": "wardrobe_incomplete"})

    lat = body.lat if body.lat is not None else user.lat
    lon = body.lon if body.lon is not None else user.lon
    weather = None
    if lat is not None and lon is not None:
        try:
            weather = get_weather(lat, lon)
        except HTTPException:
            weather = None  # still suggest something without weather

    history = list(
        db.scalars(
            select(Outfit)
            .where(Outfit.user_id == user.id, Outfit.rating != 0)
            .order_by(Outfit.created_at.desc())
            .limit(20)
        )
    )

    suggestions, ai_resp = suggest_feature.suggest(
        items, weather, body.occasion, body.note.strip(), body.lang, history,
        subject_id=user.id, tier=ent.model_tier, budget=UserBudget(user, ent), idempotency_key=idempotency_key,
    )

    saved = []
    for sug in suggestions:
        outfit = Outfit(
            user_id=user.id,
            occasion=body.occasion,
            note=body.note.strip(),
            weather=weather or {},
            item_ids=[str(i.id) for i in sug["items"]],
            title=sug["title"],
            reason=sug["reason"],
            lang=body.lang,
            prompt_version=ai_resp.prompt_version,
            ai_request_id=ai_resp.request_id,
            outfit_items=[OutfitItem(item=i, position=n, slot=i.category) for n, i in enumerate(sug["items"])],
        )
        db.add(outfit)
        saved.append(outfit)
    db.commit()

    by_id = _items_by_id(user)
    return SuggestOut(
        weather=WeatherOut(**weather) if weather else None,
        outfits=[outfit_out(o, by_id) for o in saved],
    )


@router.get("", response_model=list[OutfitOut])
def history(liked_only: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Outfit).where(Outfit.user_id == user.id)
    if liked_only:
        q = q.where(Outfit.rating == 1)
    by_id = _items_by_id(user)
    return [outfit_out(o, by_id) for o in db.scalars(q.order_by(Outfit.created_at.desc()).limit(50))]


@router.post("/{outfit_id}/feedback", response_model=OutfitOut)
def feedback(outfit_id: uuid.UUID, body: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    outfit = db.get(Outfit, outfit_id)
    if outfit is None or outfit.user_id != user.id:
        raise HTTPException(404, detail={"code": "not_found"})
    outfit.rating = body.rating
    kind = {1: "like", -1: "dislike", 0: "unrate"}[body.rating]
    db.add(FeedbackEvent(user_id=user.id, outfit_id=outfit.id, kind=kind))
    db.commit()
    return outfit_out(outfit, _items_by_id(user))
