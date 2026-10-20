import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..ai.context import build_suggest_context
from ..ai.features import suggest as suggest_feature
from ..config import get_settings
from ..db import get_db
from ..entitlements import UserBudget, entitlements, require_feature
from ..models import User
from ..ratelimit import limiter
from ..schemas import FeedbackIn, OutfitCreateIn, OutfitItemsIn, OutfitOut, SuggestIn, SuggestOut, WeatherOut
from ..security import current_user, verified_user
from ..serialize import outfit_out
from ..services import feedback as feedback_service
from ..services import orchestration
from ..services import outfits as outfits_service

router = APIRouter(prefix="/outfits", tags=["outfits"])


def _items_by_id(user: User) -> dict:
    return {str(i.id): i for i in user.items}


@router.post("/suggest", response_model=SuggestOut)
@limiter.limit(lambda: get_settings().suggest_limit)
def suggest(
    request: Request,
    body: SuggestIn,
    idempotency_key: str | None = Header(default=None, max_length=100),
    user: User = Depends(verified_user),
    db: Session = Depends(get_db),
):
    ent = entitlements(user, db)
    require_feature(ent, "suggest")
    now = datetime.now(timezone.utc)
    inputs = orchestration.suggest_inputs(db, user, body.lat, body.lon, now)
    if not suggest_feature.wardrobe_ready([i for i in inputs.items if not i.archived]):
        raise HTTPException(400, detail={"code": "wardrobe_incomplete"})

    ctx = build_suggest_context(
        inputs.items, inputs.weather_dto, body.occasion, body.note, None, inputs.profile, inputs.summary,
        inputs.recent_feedback, inputs.recently_worn, body.lang,
        today=now.date(), southern_hemisphere=inputs.southern_hemisphere,
    )
    suggestions, ai_resp = suggest_feature.suggest(
        ctx, body.lang, subject_id=user.id, tier=ent.model_tier, budget=UserBudget(user, ent),
        idempotency_key=idempotency_key,
    )
    saved = outfits_service.save_suggestions(
        db, user,
        [outfits_service.NewOutfit(s.title, s.reason, [i.id for i in s.items]) for s in suggestions],
        occasion=body.occasion, note=body.note.strip(), weather=inputs.weather, lang=body.lang,
        prompt_version=ai_resp.prompt_version, ai_request_id=ai_resp.request_id,
    )
    return SuggestOut(
        weather=WeatherOut(**inputs.weather) if inputs.weather else None,
        outfits=[outfit_out(o) for o in saved],
    )


@router.get("", response_model=list[OutfitOut])
def history(liked_only: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    by_id = _items_by_id(user)
    return [outfit_out(o, by_id) for o in outfits_service.history(db, user, liked_only)]


@router.post("", response_model=OutfitOut, status_code=201)
def create_outfit(body: OutfitCreateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A user-built outfit (source=user). Items must be the user's own and form a complete outfit."""
    require_feature(entitlements(user, db), "user_outfits")
    outfit = outfits_service.create_user_outfit(db, user, body.item_ids, body.occasion, body.title, body.lang)
    return outfit_out(outfit)


@router.patch("/{outfit_id}/items", response_model=OutfitOut)
def update_outfit_items(outfit_id: uuid.UUID, body: OutfitItemsIn, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    """Edit an outfit's pieces; an AI suggestion becomes source=ai_edited."""
    require_feature(entitlements(user, db), "user_outfits")
    return outfit_out(outfits_service.update_outfit_items(db, user, outfit_id, body.item_ids))


@router.post("/{outfit_id}/worn", response_model=OutfitOut)
def worn(outfit_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """"Wore it today": counted once per day."""
    return outfit_out(outfits_service.mark_worn(db, user, outfit_id), _items_by_id(user))


@router.post("/{outfit_id}/feedback", response_model=OutfitOut)
def feedback(outfit_id: uuid.UUID, body: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return outfit_out(feedback_service.rate(db, user, outfit_id, body.rating), _items_by_id(user))
