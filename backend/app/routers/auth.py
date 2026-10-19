from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User
from ..ratelimit import limiter
from ..schemas import DemoIn, LoginIn, RegisterIn, TokenOut, UserOut
from ..security import create_token, hash_password, verify_password
from ..services import profile
from ..services.demo import cleanup_expired_demos, create_demo_user

router = APIRouter(prefix="/auth", tags=["auth"])

# Verified against when the email is unknown, so response time doesn't reveal which emails exist.
_DUMMY_HASH = hash_password("timing-equalizer")


def _token(user: User) -> TokenOut:
    return TokenOut(token=create_token(user.id), user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenOut, status_code=201)
@limiter.limit("10/hour")
def register(request: Request, body: RegisterIn, db: Session = Depends(get_db)):
    return _token(profile.create_user(db, body.email, body.password, body.name, body.locale))


@router.post("/login", response_model=TokenOut)
@limiter.limit("20/15minutes")
def login(request: Request, body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok or user.is_demo:
        raise HTTPException(401, detail={"code": "invalid_credentials"})
    return _token(user)


@router.post("/demo", response_model=TokenOut, status_code=201)
@limiter.limit(lambda: get_settings().demo_limit)
def demo(request: Request, body: DemoIn, db: Session = Depends(get_db)):
    """A fresh, private demo account with a sample wardrobe; deleted after DEMO_TTL_HOURS."""
    cleanup_expired_demos(db)
    user = create_demo_user(db, body.locale)
    return _token(user)
