"""Items and their photos."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Item, User
from ..vocab import COLORS, PATTERNS, SEASONS, keep_known, one_of
from . import images
from .errors import bad_request, not_found


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


def active_item_count(user: User) -> int:
    """Pieces that count against the plan's max_items (design §7: archived ones don't)."""
    return sum(1 for i in user.items if i.archived_at is None)


def create_item(db: Session, user: User, values: dict, max_items: int) -> Item:
    if active_item_count(user) >= max_items:
        raise bad_request("wardrobe_full")
    # The key must be one this user uploaded via /items/analyze and not on another item yet.
    img = images.claim_upload(db, user, values["image_key"])
    raw = values.pop("ai_tags_raw", None)
    item = Item(user_id=user.id, ai_tags_raw=raw, **clean(values))
    db.add(item)
    db.flush()
    images.attach(img, item)
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
    key = item.image_key
    db.delete(item)  # outfit_items rows go with it (ON DELETE CASCADE); wardrobe_images.item_id → NULL
    db.commit()
    images.release(db, key)  # the object after the row, tolerant of bucket errors (§8)
