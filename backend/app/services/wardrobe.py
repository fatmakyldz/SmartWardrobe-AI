"""Items and their photos."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..images import new_key, normalize
from ..models import Item, User
from ..storage import get_storage
from ..vocab import COLORS, PATTERNS, SEASONS, keep_known, one_of
from .errors import bad_request, not_found


def store_upload(db: Session, user: User, raw: bytes, max_mb: int) -> tuple[str, bytes]:
    """Validate and store a photo; returns (image_key, small JPEG for the vision model)."""
    stored, small = normalize(raw, max_mb)
    key = new_key(user.id)
    get_storage().put(db, key, stored, "image/webp")
    db.commit()
    return key, small


def clean(values: dict) -> dict:
    if "colors" in values and values["colors"] is not None:
        values["colors"] = keep_known(values["colors"], COLORS, 3)
    if "seasons" in values and values["seasons"] is not None:
        values["seasons"] = keep_known(values["seasons"], SEASONS, 4)
    if "pattern" in values and values["pattern"] is not None:
        values["pattern"] = one_of(values["pattern"], PATTERNS, "solid")
    return values


def list_items(db: Session, user: User, category: str | None = None) -> list[Item]:
    q = select(Item).where(Item.user_id == user.id)
    if category:
        q = q.where(Item.category == category)
    return list(db.scalars(q.order_by(Item.created_at.desc())))


def create_item(db: Session, user: User, values: dict, max_items: int) -> Item:
    # The key must be one this user uploaded via /items/analyze.
    if not values["image_key"].startswith(f"u/{user.id.hex}/"):
        raise bad_request("invalid_image")
    if len(user.items) >= max_items:
        raise bad_request("wardrobe_full")
    item = Item(user_id=user.id, **clean(values))
    db.add(item)
    db.commit()
    return item


def own_item(db: Session, user: User, item_id: uuid.UUID) -> Item:
    item = db.get(Item, item_id)
    if item is None or item.user_id != user.id:
        raise not_found()
    return item


def update_item(db: Session, user: User, item_id: uuid.UUID, values: dict) -> Item:
    item = own_item(db, user, item_id)
    for field, value in clean(values).items():
        if value is not None:
            setattr(item, field, value)
    db.commit()
    return item


def delete_item(db: Session, user: User, item_id: uuid.UUID) -> None:
    item = own_item(db, user, item_id)
    get_storage().delete(db, [item.image_key])
    db.delete(item)  # outfit_items rows go with it (ON DELETE CASCADE)
    db.commit()
