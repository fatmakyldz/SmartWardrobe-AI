"""Accounts, profile fields, explicit style preferences and the rule-based taste summary (§10 step 8)."""

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import FeedbackEvent, Item, Outfit, User
from ..security import hash_password
from . import images

SUMMARY_EVERY_EVENTS = 10
SUMMARY_MAX_AGE = timedelta(days=7)
SUMMARY_WINDOW = 30  # most recent like / dislike / worn events

COLOR_TR = {
    "black": "siyah", "white": "beyaz", "grey": "gri", "navy": "lacivert", "blue": "mavi", "lightblue": "açık mavi",
    "green": "yeşil", "olive": "haki", "beige": "bej", "cream": "krem", "brown": "kahverengi", "khaki": "haki",
    "red": "kırmızı", "burgundy": "bordo", "pink": "pembe", "purple": "mor", "yellow": "sarı", "orange": "turuncu",
    "gold": "altın", "silver": "gümüş", "multi": "çok renkli",
}


def aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; everything here is UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── accounts ──────────────────────────────────────────────────────────────

def create_user(db: Session, email: str, password: str, name: str, locale: str) -> User:
    email = email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(409, detail={"code": "email_taken"})
    user = User(email=email, password_hash=hash_password(password), name=name.strip(), locale=locale)
    db.add(user)
    db.commit()
    return user


def mark_verified(user: User, now: datetime | None = None) -> None:
    """The caller commits (with the spent token)."""
    if user.email_verified_at is None:
        user.email_verified_at = now or datetime.now(timezone.utc)


def set_password(user: User, password: str) -> None:
    """The caller commits, together with signing every session out."""
    user.password_hash = hash_password(password)


def update_profile(db: Session, user: User, values: dict) -> User:
    for field, value in values.items():
        setattr(user, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    return user


def delete_account(db: Session, user: User) -> None:
    """Account, wardrobe, outfits, feedback and photos. ai_requests keep only the pseudonymous id.
    One transaction for the rows (wardrobe_images go by cascade), then the photo objects (§9)."""
    user_id = user.id
    db.delete(user)
    db.commit()
    images.delete_user_objects(db, user_id)


# ── explicit style preferences ────────────────────────────────────────────

def update_style(db: Session, user: User, patch: dict) -> dict:
    """Merge validated fields into users.style_profile: answers per question, lists replaced whole."""
    profile = dict(user.style_profile or {})
    if patch.get("answers") is not None:
        answers = dict(profile.get("answers") or {})
        for k, v in patch["answers"].items():  # exclude_unset upstream: a key given as None clears it
            if v is None:
                answers.pop(k, None)
            else:
                answers[k] = v
        profile["answers"] = answers
    for key in ("liked_colors", "disliked_colors", "styles", "avoid"):
        if patch.get(key) is not None:
            profile[key] = list(dict.fromkeys(patch[key]))
    user.style_profile = profile  # reassign so the JSON column is marked dirty
    db.commit()
    return profile


# ── taste summary ─────────────────────────────────────────────────────────

def outfit_items(db: Session, outfit: Outfit) -> list[Item]:
    """Current pieces of an outfit: outfit_items, or item_ids for rows written before 0002."""
    if outfit.outfit_items:
        return [oi.item for oi in outfit.outfit_items]
    ids = [i for i in (outfit.item_ids or [])]
    if not ids:
        return []
    by_id = {str(i.id): i for i in db.scalars(select(Item).where(Item.user_id == outfit.user_id))}
    return [by_id[i] for i in ids if i in by_id]


def _join(words: list[str], lang: str) -> str:
    if len(words) <= 1:
        return "".join(words)
    return f"{', '.join(words[:-1])} {'ve' if lang == 'tr' else 'and'} {words[-1]}"


def build_summary(liked: list[Item], disliked: list[Item], lang: str) -> str | None:
    """3–4 template sentences from colour, piece and formality counts. No LLM."""
    if not liked and not disliked:
        return None
    tr = lang == "tr"
    color = (lambda c: COLOR_TR.get(c, c)) if tr else (lambda c: c)
    pos_colors = Counter(c for i in liked for c in i.colors)
    neg_colors = Counter(c for i in disliked for c in i.colors)
    pieces = Counter(i.subcategory or i.category for i in liked)
    top_colors = [c for c, _ in pos_colors.most_common(3)]
    avoid = [c for c, _ in neg_colors.most_common(5) if c not in top_colors][:2]

    sentences = []
    if top_colors:
        names = _join([color(c) for c in top_colors], lang)
        sentences.append(f"{names.capitalize()} parçaları seviyor." if tr else f"Likes {names} pieces.")
    if pieces:
        names = _join([p for p, _ in pieces.most_common(3)], lang)
        sentences.append(f"Sık seçtikleri: {names}." if tr else f"Often picks {names}.")
    if liked:
        avg = sum(i.formality for i in liked) / len(liked)
        level = 0 if avg < 2.5 else 1 if avg < 3.5 else 2
        sentences.append(("Tarzı daha çok günlük.", "Tarzı şık-günlük.", "Tarzı daha çok resmi.")[level] if tr
                         else ("Leans casual.", "Leans smart-casual.", "Leans formal.")[level])
    if avoid:
        names = _join([color(c) for c in avoid], lang)
        sentences.append(f"{names.capitalize()} tonlarını pek sevmiyor." if tr else f"Tends to skip {names}.")
    return " ".join(sentences) or None


def refresh_style_summary(db: Session, user: User, now: datetime | None = None) -> str | None:
    now = now or datetime.now(timezone.utc)
    events = db.scalars(
        select(FeedbackEvent)
        .where(FeedbackEvent.user_id == user.id, FeedbackEvent.kind.in_(("like", "dislike", "worn")),
               FeedbackEvent.outfit_id.is_not(None))
        .order_by(FeedbackEvent.created_at.desc())
        .limit(SUMMARY_WINDOW)
    ).all()
    liked, disliked = [], []
    for e in events:
        outfit = db.get(Outfit, e.outfit_id)
        if outfit is None:
            continue
        (disliked if e.kind == "dislike" else liked).extend(outfit_items(db, outfit))
    user.style_summary = build_summary(liked, disliked, user.locale)
    user.style_summary_at = now
    db.commit()
    return user.style_summary


def maybe_refresh_style_summary(db: Session, user: User, now: datetime | None = None) -> bool:
    """Every 10 events, or when the summary is older than 7 days (or missing). Cheap, so synchronous."""
    now = now or datetime.now(timezone.utc)
    at = aware(user.style_summary_at)
    if at is not None and now - at < SUMMARY_MAX_AGE:
        since = db.scalar(select(func.count()).select_from(FeedbackEvent)
                          .where(FeedbackEvent.user_id == user.id, FeedbackEvent.created_at > at))
        if since < SUMMARY_EVERY_EVENTS:
            return False
    refresh_style_summary(db, user, now)
    return True
