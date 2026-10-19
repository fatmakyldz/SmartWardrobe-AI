import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import ai
from ..config import get_settings
from ..db import get_db
from ..images import data_url, new_key, normalize
from ..models import Item, User
from ..ratelimit import limiter
from ..schemas import AnalyzeOut, ItemIn, ItemOut, ItemUpdate, Tags
from ..security import current_user
from ..serialize import item_out
from ..storage import get_storage
from ..vocab import COLORS, PATTERNS, SEASONS, keep_known, one_of

router = APIRouter(prefix="/items", tags=["items"])


@router.post("/analyze", response_model=AnalyzeOut)
@limiter.limit(lambda: get_settings().analyze_limit)
def analyze(
    request: Request,
    image: UploadFile = File(...),
    lang: str = Form("en"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Store the photo and let the vision model pre-fill the tags. The user confirms with POST /items."""
    # Plain `def`: FastAPI runs it in the threadpool, so Pillow, the storage upload,
    # the DB commit and the Groq call never block the event loop.
    s = get_settings()
    raw = image.file.read(s.max_upload_mb * 1024 * 1024 + 1)
    stored, small = normalize(raw, s.max_upload_mb)

    key = new_key(user.id)
    storage = get_storage()
    storage.put(db, key, stored, "image/webp")
    db.commit()

    tags = ai.tag_image(data_url(small), "tr" if lang == "tr" else "en")
    is_clothing = tags.pop("is_clothing")
    return AnalyzeOut(image_key=key, image_url=storage.url(key), is_clothing=is_clothing, tags=Tags(**tags))


def _clean(values: dict) -> dict:
    if "colors" in values and values["colors"] is not None:
        values["colors"] = keep_known(values["colors"], COLORS, 3)
    if "seasons" in values and values["seasons"] is not None:
        values["seasons"] = keep_known(values["seasons"], SEASONS, 4)
    if "pattern" in values and values["pattern"] is not None:
        values["pattern"] = one_of(values["pattern"], PATTERNS, "solid")
    return values


@router.post("", response_model=ItemOut, status_code=201)
def create_item(body: ItemIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    # The key must be one this user uploaded via /items/analyze.
    if not body.image_key.startswith(f"u/{user.id.hex}/"):
        raise HTTPException(400, detail={"code": "invalid_image"})
    if len(user.items) >= get_settings().max_items:
        raise HTTPException(400, detail={"code": "wardrobe_full"})
    item = Item(user_id=user.id, **_clean(body.model_dump()))
    db.add(item)
    db.commit()
    return item_out(item)


@router.get("", response_model=list[ItemOut])
def list_items(category: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Item).where(Item.user_id == user.id)
    if category:
        q = q.where(Item.category == category)
    return [item_out(i) for i in db.scalars(q.order_by(Item.created_at.desc()))]


def _own_item(db: Session, user: User, item_id: uuid.UUID) -> Item:
    item = db.get(Item, item_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, detail={"code": "not_found"})
    return item


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(item_id: uuid.UUID, body: ItemUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = _own_item(db, user, item_id)
    for field, value in _clean(body.model_dump(exclude_unset=True)).items():
        if value is not None:
            setattr(item, field, value)
    db.commit()
    return item_out(item)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = _own_item(db, user, item_id)
    get_storage().delete(db, [item.image_key])
    db.delete(item)
    db.commit()
    return Response(status_code=204)
