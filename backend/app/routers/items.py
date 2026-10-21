import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session

from ..ai import analysis
from ..ai.context import season_of
from ..ai.features import tagging
from ..config import get_settings
from ..db import get_db
from ..entitlements import UserBudget, entitlements, require_feature
from ..models import User
from ..ratelimit import limiter
from ..schemas import AnalyzeOut, GapOut, ItemIn, ItemOut, ItemUpdate, Tags, WardrobeAnalysisOut
from ..security import current_user, is_verified
from ..serialize import item_out
from ..services import images, orchestration, wardrobe
from ..storage import get_storage

router = APIRouter(prefix="/items", tags=["items"])


@router.post("/analyze", response_model=AnalyzeOut)
@limiter.limit(lambda: get_settings().analyze_limit)
def analyze(
    request: Request,
    image: UploadFile = File(...),
    lang: str = Form("en"),
    idempotency_key: str | None = Header(default=None, max_length=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Store the photo and let the vision model pre-fill the tags. The user confirms with POST /items.
    Without a verified email the photo is still stored (the wardrobe is open, §14 C3) but the model is
    not called: empty tags come back with ai_skipped="email_unverified" for the user to fill in."""
    # Plain `def`: FastAPI runs it in the threadpool, so Pillow, the storage upload,
    # the DB commit and the model call never block the event loop.
    ent = entitlements(user, db)
    require_feature(ent, "tagging")

    s = get_settings()
    key, small = images.store_upload(db, user, image.file.read(s.max_upload_mb * 1024 * 1024 + 1), s.max_upload_mb)
    lang = "tr" if lang == "tr" else "en"
    if not is_verified(user):
        return AnalyzeOut(image_key=key, image_url=get_storage().url(key), is_clothing=True,
                          tags=Tags(category="top"), ai_skipped="email_unverified")

    # The same photo sent twice within a minute (double tap, retry) is tagged once.
    same_photo = idempotency_key or f"{hashlib.sha256(small).hexdigest()}:{lang}"
    out, _ = tagging.tag_image(small, lang, subject_id=user.id, tier=ent.model_tier,
                               budget=UserBudget(user, ent), idempotency_key=same_photo)
    tags = out.model_dump()
    is_clothing = tags.pop("is_clothing")
    return AnalyzeOut(image_key=key, image_url=get_storage().url(key), is_clothing=is_clothing, tags=Tags(**tags))


@router.post("", response_model=ItemOut, status_code=201)
def create_item(body: ItemIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return item_out(wardrobe.create_item(db, user, body.model_dump(), entitlements(user, db).max_items))


@router.get("", response_model=list[ItemOut])
def list_items(category: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [item_out(i) for i in wardrobe.list_items(db, user, category)]


@router.get("/analysis", response_model=WardrobeAnalysisOut)
@limiter.limit(lambda: get_settings().analyze_limit)
def wardrobe_analysis(request: Request, lat: float | None = Query(default=None, ge=-90, le=90),
                      user: User = Depends(current_user)):
    """What the wardrobe is missing (AI-06, deterministic: no AI request, every plan). `lat` only picks
    the hemisphere for the season."""
    inputs = orchestration.wardrobe_inputs(user, lat)
    season = season_of(datetime.now(timezone.utc).date(), inputs.southern_hemisphere)
    result = analysis.analyze(inputs.items, season)
    return WardrobeAnalysisOut(
        season=result.season, items=result.stats.items, per_category=result.stats.per_category,
        outfits_possible=result.stats.outfits_possible, neutral_share=result.stats.neutral_share,
        gaps=[GapOut(code=g.code, category=g.category, occasion=g.occasion, season=g.season, severity=g.severity,
                     item_ids=list(g.item_ids)) for g in result.gaps],
    )


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(item_id: uuid.UUID, body: ItemUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return item_out(wardrobe.update_item(db, user, item_id, body.model_dump(exclude_unset=True)))


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    wardrobe.delete_item(db, user, item_id)
    return Response(status_code=204)
