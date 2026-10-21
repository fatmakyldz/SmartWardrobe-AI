import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

_hasher = PasswordHash.recommended()  # Argon2id
_bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(password, hashed)
    except Exception:
        return False


def create_access_token(user: User) -> str:
    """Short-lived (15 min). `tv` = users.token_version: bumping it signs every device out at once."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "iat": now, "exp": now + timedelta(minutes=s.access_token_minutes),
               "tv": user.token_version}
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "unauthorized"},
        headers={"WWW-Authenticate": "Bearer"},
    )


def user_from_access_token(db: Session, token: str) -> User | None:
    """The user an access token stands for, or None when it is invalid, expired or signed out."""
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM],
                             options={"require": ["exp", "sub", "tv"]})
        user_id = uuid.UUID(payload["sub"])
        version = int(payload["tv"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None
    user = db.get(User, user_id)
    return user if user is not None and user.token_version == version else None


def current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise _unauthorized()
    user = user_from_access_token(db, creds.credentials)
    if user is None:
        raise _unauthorized()
    # Lets the rate limiter key on the user instead of the IP.
    request.state.user_id = str(user.id)
    return user


def is_verified(user: User) -> bool:
    """AI features need a verified email (§14 C3); demo accounts are exempt."""
    return user.is_demo or user.email_verified_at is not None


def verified_user(user: User = Depends(current_user)) -> User:
    if not is_verified(user):
        raise HTTPException(403, detail={"code": "email_unverified"})
    return user
