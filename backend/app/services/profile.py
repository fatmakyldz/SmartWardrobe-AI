"""Accounts, profile fields, explicit style preferences and the rule-based taste summary (§10 step 8)."""

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import AIRequest, FeedbackEvent, Item, Outfit, RefreshToken, UsageCounter, User
from ..storage import get_storage
from ..security import hash_password
from ..vocab import normalize_lang
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


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def export_account(db: Session, user: User, now: datetime | None = None) -> dict:
    """Everything the account holds, as plain JSON (data portability, §9): profile, style answers, pieces
    (tags + a short-lived photo link), outfits with their pieces, feedback events, sign-in sessions, and the
    usage records still linked to the account (daily counters; AI requests younger than the 90-day
    anonymisation — feature, status, tokens, time; never prompts). Read-only."""
    now = now or datetime.now(timezone.utc)
    storage = get_storage()
    items = db.scalars(select(Item).where(Item.user_id == user.id).order_by(Item.created_at)).all()
    outfits = db.scalars(
        select(Outfit).where(Outfit.user_id == user.id).options(selectinload(Outfit.outfit_items)).order_by(Outfit.created_at)
    ).all()
    feedback = db.scalars(select(FeedbackEvent).where(FeedbackEvent.user_id == user.id).order_by(FeedbackEvent.created_at)).all()
    sessions = db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None),
                                                     RefreshToken.expires_at > now).order_by(RefreshToken.created_at)).all()
    counters = db.scalars(select(UsageCounter).where(UsageCounter.user_id == user.id)
                          .order_by(UsageCounter.period_start, UsageCounter.feature)).all()
    requests = db.scalars(select(AIRequest).where(AIRequest.subject_id == user.id).order_by(AIRequest.created_at)).all()
    return {
        "format": "smartwardrobe-export/1",
        "exported_at": now.isoformat(),
        "account": {
            "email": user.email, "name": user.name, "locale": user.locale, "timezone": user.timezone,
            "city": user.city, "lat": user.lat, "lon": user.lon, "plan": user.plan,
            "created_at": _iso(user.created_at), "email_verified_at": _iso(user.email_verified_at),
            "onboarding_completed_at": _iso(user.onboarding_completed_at),
        },
        "style": {"answers": user.style_profile or {}, "summary": user.style_summary, "summary_at": _iso(user.style_summary_at)},
        "items": [
            {
                "id": str(i.id), "name": i.name, "category": i.category, "subcategory": i.subcategory,
                "colors": i.colors or [], "pattern": i.pattern, "warmth": i.warmth, "formality": i.formality,
                "seasons": i.seasons or [], "brand": i.brand, "material": i.material, "is_favorite": i.is_favorite,
                "wear_count": i.wear_count, "last_worn_at": _iso(i.last_worn_at), "archived_at": _iso(i.archived_at),
                "ai_confidence": i.ai_confidence, "ai_tags_raw": i.ai_tags_raw, "created_at": _iso(i.created_at),
                # s3 mode: a presigned link that expires in minutes — download the photos with the export.
                # db mode (local only): an /images/ path that needs the bearer token.
                "photo_url": storage.url(i.image_key),
            }
            for i in items
        ],
        "outfits": [
            {
                "id": str(o.id), "title": o.title, "reason": o.reason, "occasion": o.occasion, "note": o.note,
                "weather": o.weather or {}, "source": o.source, "rating": o.rating, "lang": o.lang,
                "worn_at": _iso(o.worn_at), "created_at": _iso(o.created_at),
                "item_ids": [str(oi.item_id) for oi in sorted(o.outfit_items, key=lambda oi: oi.position)] or list(o.item_ids or []),
            }
            for o in outfits
        ],
        "feedback": [
            {"kind": f.kind, "outfit_id": str(f.outfit_id) if f.outfit_id else None,
             "item_id": str(f.item_id) if f.item_id else None, "created_at": _iso(f.created_at)}
            for f in feedback
        ],
        "sessions": [
            {"device": s.device_label, "signed_in_at": _iso(s.created_at), "last_used_at": _iso(s.last_used_at), "expires_at": _iso(s.expires_at)}
            for s in sessions
        ],
        "usage": {
            "daily_counters": [
                {"day": c.period_start.isoformat(), "feature": c.feature, "requests": c.count, "tokens": c.tokens} for c in counters
            ],
            "ai_requests": [
                {"feature": r.feature, "status": r.status, "created_at": _iso(r.created_at),
                 "input_tokens": r.input_tokens_total, "output_tokens": r.output_tokens_total}
                for r in requests
            ],
        },
    }


def delete_account(db: Session, user: User) -> None:
    """Account, wardrobe, outfits, feedback and photos. ai_requests keep only the pseudonymous id.
    One transaction for the rows (wardrobe_images go by cascade), then the photo objects (§9)."""
    user_id = user.id
    db.delete(user)
    db.commit()
    images.delete_user_objects(db, user_id)


UNVERIFIED_TTL = timedelta(days=14)


def cleanup_stale_unverified(db: Session, now: datetime | None = None, dry_run: bool = False, limit: int = 100) -> list[str]:
    """Accounts that never confirmed their email and have not been used for UNVERIFIED_TTL (no refresh
    token used or issued since) are deleted with their photos, like expired demo accounts (C3 (a′): an
    unverified account is a disposable one until it isn't). Returns the ids handled."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - UNVERIFIED_TTL
    last_use = (
        select(RefreshToken.user_id, func.max(func.coalesce(RefreshToken.last_used_at, RefreshToken.created_at)).label("at"))
        .group_by(RefreshToken.user_id)
        .subquery()
    )
    stale = db.scalars(
        select(User)
        .outerjoin(last_use, last_use.c.user_id == User.id)
        .where(User.is_demo.is_(False), User.email_verified_at.is_(None), User.created_at < cutoff,
               or_(last_use.c.at.is_(None), last_use.c.at < cutoff))
        .limit(limit)
    ).all()
    ids = [str(u.id) for u in stale]
    if not dry_run:
        for u in stale:
            delete_account(db, u)
    return ids


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
    return f"{', '.join(words[:-1])} {'ve' if normalize_lang(lang) == 'tr' else 'and'} {words[-1]}"


WORN_WEIGHT = 2  # wearing an outfit says more than liking it
PATTERN_SHARE = 0.25  # a non-plain pattern on this share of liked pieces is a taste, not a one-off
NOT_A_TASTE = ('solid', 'other', 'denim')  # jeans are in every wardrobe; denim says nothing about taste
LAYER_SHARE = 0.5  # outerwear in this share of liked outfits → "usually adds a layer"
MAX_SENTENCES = 8  # all eight candidates ≈ 60–90 tokens; the TASTE SUMMARY line is budgeted at ~150 (§6)

PATTERN_TR = {"striped": "çizgili", "checked": "ekose", "floral": "çiçekli", "printed": "desenli", "denim": "kot",
              "knit": "triko", "leather": "deri"}


def build_summary(liked: list[list[Item]], disliked: list[list[Item]], lang: str,
                  worn: list[list[Item]] | None = None) -> str | None:
    """Up to eight template sentences, no LLM: colours, pieces, formality, what gets skipped, patterns, the
    go-to combination and layering. Inputs are outfits (lists of pieces); worn outfits count double for
    the counts, but habits (combination, layering) need at least two distinct outfits."""
    worn = worn or []
    if not liked and not disliked and not worn:
        return None
    tr = normalize_lang(lang) == "tr"  # templates exist in EN and TR; any other language reads the EN ones
    color = (lambda c: COLOR_TR.get(c, c)) if tr else (lambda c: c)
    pattern = (lambda x: PATTERN_TR.get(x, x)) if tr else (lambda x: x)

    positive = liked + worn * WORN_WEIGHT  # outfit lists; a worn outfit appears twice
    observed = len(liked) + len(worn)  # distinct outfits, for the habit thresholds
    pos_items = [i for o in positive for i in o]
    neg_items = [i for o in disliked for i in o]
    pos_colors = Counter(c for i in pos_items for c in i.colors)
    neg_colors = Counter(c for i in neg_items for c in i.colors)
    pieces = Counter(i.subcategory or i.category for i in pos_items)
    top_colors = [c for c, _ in pos_colors.most_common(3)]
    avoid = [c for c, _ in neg_colors.most_common(5) if c not in top_colors][:2]

    sentences = []
    if top_colors:
        names = _join([color(c) for c in top_colors], lang)
        sentences.append(f"{names.capitalize()} parçaları seviyor." if tr else f"Likes {names} pieces.")
    if pieces:
        names = _join([p for p, _ in pieces.most_common(3)], lang)
        sentences.append(f"Sık seçtikleri: {names}." if tr else f"Often picks {names}.")
    if pos_items:
        avg = sum(i.formality for i in pos_items) / len(pos_items)
        level = 0 if avg < 2.5 else 1 if avg < 3.5 else 2
        sentences.append(("Tarzı daha çok günlük.", "Tarzı şık-günlük.", "Tarzı daha çok resmi.")[level] if tr
                         else ("Leans casual.", "Leans smart-casual.", "Leans formal.")[level])
    if avoid:
        names = _join([color(c) for c in avoid], lang)
        sentences.append(f"{names.capitalize()} tonlarını pek sevmiyor." if tr else f"Tends to skip {names}.")

    # Patterns: a non-plain pattern on a real share of what they like; the one they skip most.
    pos_patterns = Counter(i.pattern for i in pos_items if i.pattern and i.pattern not in NOT_A_TASTE)
    if pos_patterns:
        pat, n = pos_patterns.most_common(1)[0]
        if n / len(pos_items) >= PATTERN_SHARE:
            sentences.append(f"{pattern(pat).capitalize()} parçalara sıcak bakıyor." if tr else f"Likes {pattern(pat)} pieces.")
    neg_patterns = Counter(i.pattern for i in neg_items if i.pattern and i.pattern not in NOT_A_TASTE)
    if neg_patterns:
        pat, n = neg_patterns.most_common(1)[0]
        if n >= 2 and pos_patterns.get(pat, 0) == 0:
            sentences.append(f"{pattern(pat).capitalize()} desenleri pek giymiyor." if tr else f"Skips {pattern(pat)} pieces.")

    # The go-to combination: the most frequent (top, bottom) pair by piece type, or a dress, seen in at
    # least two distinct outfits (ties: liked before worn, newest first within each).
    combos = Counter()
    for o in liked + worn:
        top = next((i for i in o if i.category == "top"), None)
        bottom = next((i for i in o if i.category == "bottom"), None)
        dress = next((i for i in o if i.category == "dress"), None)
        if top and bottom:
            combos[f"{top.subcategory or 'top'} + {bottom.subcategory or 'bottom'}"] += 1
        elif dress:
            combos[dress.subcategory or "dress"] += 1
    if combos:
        combo, n = combos.most_common(1)[0]
        if n >= 2:
            sentences.append(f"Vazgeçmediği ikili: {combo}." if tr else f"Go-to combination: {combo}.")

    # Layers: outerwear in most of the (distinct) outfits they liked or wore.
    if observed >= 2:
        layered = sum(1 for o in liked + worn if any(i.category == "outerwear" for i in o))
        if layered / observed >= LAYER_SHARE:
            sentences.append("Genelde üstüne bir kat alıyor." if tr else "Usually adds a layer.")
    return " ".join(sentences[:MAX_SENTENCES]) or None


def refresh_style_summary(db: Session, user: User, now: datetime | None = None) -> str | None:
    now = now or datetime.now(timezone.utc)
    events = db.scalars(
        select(FeedbackEvent)
        .where(FeedbackEvent.user_id == user.id, FeedbackEvent.kind.in_(("like", "dislike", "worn")),
               FeedbackEvent.outfit_id.is_not(None))
        .order_by(FeedbackEvent.created_at.desc())
        .limit(SUMMARY_WINDOW)
    ).all()
    liked, disliked, worn = [], [], []
    for e in events:
        outfit = db.get(Outfit, e.outfit_id)
        if outfit is None:
            continue
        pieces = outfit_items(db, outfit)
        (disliked if e.kind == "dislike" else worn if e.kind == "worn" else liked).append(pieces)
    user.style_summary = build_summary(liked, disliked, user.locale, worn)
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
