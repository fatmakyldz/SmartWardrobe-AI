"""👍 / 👎: the latest state on outfits.rating, the history in feedback_events."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import FeedbackEvent, Outfit, User
from .outfits import own_outfit
from .profile import maybe_refresh_style_summary

KIND = {1: "like", -1: "dislike", 0: "unrate"}


def rate(db: Session, user: User, outfit_id: uuid.UUID, rating: int, now: datetime | None = None) -> Outfit:
    now = now or datetime.now(timezone.utc)
    outfit = own_outfit(db, user, outfit_id)
    outfit.rating = rating
    db.add(FeedbackEvent(user_id=user.id, outfit_id=outfit.id, kind=KIND[rating], created_at=now))
    db.commit()
    maybe_refresh_style_summary(db, user, now)
    return outfit
