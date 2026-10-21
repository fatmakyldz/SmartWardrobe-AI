"""Outfits: saving AI suggestions, user-built outfits, editing, "worn today"."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import FeedbackEvent, Item, Outfit, OutfitItem, User
from ..outfit_rules import valid_item_set
from .errors import bad_request, not_found
from .profile import aware, maybe_refresh_style_summary, outfit_items

MAX_ITEMS_PER_OUTFIT = 10


@dataclass(frozen=True)
class NewOutfit:
    """An AI suggestion as plain data (services never import app.ai)."""

    title: str
    reason: str
    item_ids: list[uuid.UUID]


def _load(db: Session):
    return select(Outfit).options(selectinload(Outfit.outfit_items).selectinload(OutfitItem.item))


def history(db: Session, user: User, liked_only: bool = False, limit: int = 50) -> list[Outfit]:
    q = _load(db).where(Outfit.user_id == user.id)
    if liked_only:
        q = q.where(Outfit.rating == 1)
    return list(db.scalars(q.order_by(Outfit.created_at.desc()).limit(limit)))


def own_outfit(db: Session, user: User, outfit_id: uuid.UUID) -> Outfit:
    outfit = db.scalar(_load(db).where(Outfit.id == outfit_id))
    if outfit is None or outfit.user_id != user.id:
        raise not_found()
    return outfit


def _own_items(db: Session, user: User, item_ids: list[uuid.UUID]) -> list[Item]:
    """The user's items in the given order; someone else's or unknown ids are a 404, like any other lookup."""
    found = {i.id: i for i in db.scalars(select(Item).where(Item.id.in_(item_ids)))}
    items = []
    for item_id in item_ids:
        item = found.get(item_id)
        if item is None or item.user_id != user.id:
            raise not_found()
        items.append(item)
    return items


def _set_items(db: Session, outfit: Outfit, items: list[Item]) -> None:
    outfit.outfit_items.clear()
    db.flush()  # delete the old rows before inserting new ones with the same (outfit_id, item_id)
    outfit.outfit_items.extend(OutfitItem(item=i, position=n, slot=i.category) for n, i in enumerate(items))


def _checked_items(db: Session, user: User, item_ids: list[uuid.UUID]) -> list[Item]:
    if not 1 <= len(item_ids) <= MAX_ITEMS_PER_OUTFIT:
        raise bad_request("invalid_outfit")
    items = _own_items(db, user, item_ids)
    if not valid_item_set(items):
        raise bad_request("invalid_outfit")
    return items


def save_suggestions(db: Session, user: User, suggestions: list[NewOutfit], *, occasion: str, note: str,
                     weather: dict | None, lang: str, prompt_version: str,
                     ai_request_id: uuid.UUID | None) -> list[Outfit]:
    saved = []
    for sug in suggestions:
        items = _own_items(db, user, sug.item_ids)
        outfit = Outfit(user_id=user.id, occasion=occasion, note=note, weather=weather or {}, title=sug.title,
                        reason=sug.reason, lang=lang, source="ai", prompt_version=prompt_version,
                        ai_request_id=ai_request_id,
                        outfit_items=[OutfitItem(item=i, position=n, slot=i.category) for n, i in enumerate(items)])
        db.add(outfit)
        saved.append(outfit)
    db.commit()
    return saved


def create_user_outfit(db: Session, user: User, item_ids: list[uuid.UUID], occasion: str, title: str,
                       lang: str) -> Outfit:
    items = _checked_items(db, user, item_ids)
    outfit = Outfit(user_id=user.id, occasion=occasion, note="", weather={}, title=title.strip(), reason="",
                    lang=lang, source="user",
                    outfit_items=[OutfitItem(item=i, position=n, slot=i.category) for n, i in enumerate(items)])
    db.add(outfit)
    db.commit()
    return outfit


def update_outfit_items(db: Session, user: User, outfit_id: uuid.UUID, item_ids: list[uuid.UUID]) -> Outfit:
    outfit = own_outfit(db, user, outfit_id)
    items = _checked_items(db, user, item_ids)
    _set_items(db, outfit, items)
    if outfit.source == "ai":
        outfit.source = "ai_edited"
    db.commit()
    return outfit


def _local_day(dt: datetime, tz_name: str | None):
    try:
        zone = ZoneInfo(tz_name) if tz_name else timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone.utc
    return aware(dt).astimezone(zone).date()


def mark_worn(db: Session, user: User, outfit_id: uuid.UUID, now: datetime | None = None) -> Outfit:
    """worn_at, wear_count / last_worn_at on each piece, a "worn" event. Counted once per day (user's timezone)."""
    now = now or datetime.now(timezone.utc)
    outfit = own_outfit(db, user, outfit_id)
    if outfit.worn_at is not None and _local_day(outfit.worn_at, user.timezone) == _local_day(now, user.timezone):
        return outfit
    outfit.worn_at = now
    for item in outfit_items(db, outfit):
        item.wear_count = (item.wear_count or 0) + 1
        item.last_worn_at = now
    db.add(FeedbackEvent(user_id=user.id, outfit_id=outfit.id, kind="worn", created_at=now))
    db.commit()
    maybe_refresh_style_summary(db, user, now)
    return outfit
