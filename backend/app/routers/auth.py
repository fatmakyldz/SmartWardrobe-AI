from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..demo import cleanup_expired_demos, create_demo_user
from ..models import User
from ..ratelimit import limiter
from ..schemas import DemoIn, LoginIn, RegisterIn, TokenOut, UserOut
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Verified against when the email is unknown, so response time doesn't reveal which emails exist.
_DUMMY_HASH = hash_password("timing-equalizer")


def _token(user: User) -> TokenOut:
    return TokenOut(token=create_token(user.id), user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenOut, status_code=201)
@limiter.limit("10/hour")
def register(request: Request, body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(409, detail={"code": "email_taken"})
    user = User(email=email, password_hash=hash_password(body.password), name=body.name.strip(), locale=body.locale)
    db.add(user)
    db.commit()
    return _token(user)


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
