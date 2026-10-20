"""Refresh tokens and single-use email tokens (§9): security's narrow writer of refresh_tokens / auth_tokens.

Raw tokens are 32 random bytes, handed out once; only their sha256 is stored.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AuthToken, RefreshToken, User

# A token rotated this recently and presented again is a lost race (two tabs refreshing at once),
# not theft: refused without revoking the family. Nothing is issued for it either way.
ROTATION_GRACE = timedelta(seconds=20)
EMAIL_TOKEN_TTL = {"verify_email": timedelta(hours=24), "reset_password": timedelta(hours=1)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _unauthorized(code: str) -> HTTPException:
    return HTTPException(401, detail={"code": code})


# ── refresh tokens ────────────────────────────────────────────────────────

def issue_refresh(db: Session, user: User, family_id: uuid.UUID | None = None, device_label: str = "") -> tuple[str, RefreshToken]:
    raw = secrets.token_urlsafe(32)
    now = _now()
    row = RefreshToken(user_id=user.id, token_hash=digest(raw), family_id=family_id or uuid.uuid4(),
                       device_label=device_label[:120], created_at=now,
                       expires_at=now + timedelta(days=get_settings().refresh_token_days))
    db.add(row)
    db.flush()
    return raw, row


def rotate(db: Session, raw: str) -> tuple[User, str]:
    """A used refresh token for a new one in the same family. Presenting a token that was already
    rotated or revoked (outside the grace window) revokes its whole family: someone else has it."""
    now = _now()
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest(raw)))
    if row is None:
        raise _unauthorized("invalid_refresh")
    if row.revoked_at is not None:
        if row.replaced_by is not None and now - _aware(row.revoked_at) < ROTATION_GRACE:
            raise _unauthorized("refresh_superseded")
        revoke_family(db, row.family_id, now)
        db.commit()
        raise _unauthorized("refresh_reused")
    if _aware(row.expires_at) <= now:
        raise _unauthorized("invalid_refresh")
    user = db.get(User, row.user_id)
    new_raw, new_row = issue_refresh(db, user, row.family_id, row.device_label)
    row.revoked_at, row.replaced_by, row.last_used_at = now, new_row.id, now
    db.commit()
    return user, new_raw


def revoke(db: Session, raw: str) -> None:
    """Logout on one device: that token (unknown or already revoked tokens are ignored)."""
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest(raw)))
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()
        db.commit()


def revoke_family(db: Session, family_id: uuid.UUID, now: datetime | None = None) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=now or _now()))


def revoke_all(db: Session, user: User) -> None:
    """Every device: all refresh tokens, and token_version++ so live access tokens die too.
    The caller commits (with the password change, for a reset)."""
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=_now()))
    user.token_version = (user.token_version or 0) + 1


# ── email tokens ──────────────────────────────────────────────────────────

def issue_email_token(db: Session, user: User, purpose: str) -> str:
    """One live token per purpose: issuing a new one uses up the older ones. The caller commits."""
    now = _now()
    db.execute(update(AuthToken).where(AuthToken.user_id == user.id, AuthToken.purpose == purpose,
                                       AuthToken.used_at.is_(None)).values(used_at=now))
    raw = secrets.token_urlsafe(32)
    db.add(AuthToken(user_id=user.id, purpose=purpose, token_hash=digest(raw),
                     expires_at=now + EMAIL_TOKEN_TTL[purpose]))
    return raw


def use_email_token(db: Session, raw: str, purpose: str) -> User:
    """Spend a token: unknown, wrong purpose, used or expired → 400 invalid_token. The caller commits."""
    row = db.scalar(select(AuthToken).where(AuthToken.token_hash == digest(raw), AuthToken.purpose == purpose))
    now = _now()
    if row is None or row.used_at is not None or _aware(row.expires_at) <= now:
        raise HTTPException(400, detail={"code": "invalid_token"})
    row.used_at = now
    return db.get(User, row.user_id)
