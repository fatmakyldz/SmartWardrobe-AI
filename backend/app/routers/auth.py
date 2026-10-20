from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import tokens
from ..config import get_settings
from ..db import get_db
from ..models import User
from ..ratelimit import limiter
from ..schemas import AuthOut, DemoIn, ForgotIn, LoginIn, RefreshIn, RegisterIn, ResetIn, TokenIn, UserOut
from ..security import create_access_token, current_user, hash_password, verify_password
from ..services import email, profile
from ..services.demo import cleanup_expired_demos, create_demo_user

router = APIRouter(prefix="/auth", tags=["auth"])

# Verified against when the email is unknown, so response time doesn't reveal which emails exist.
_DUMMY_HASH = hash_password("timing-equalizer")

# The web app sends this header: its refresh token then travels only as an httpOnly cookie.
COOKIE_HEADER = "X-Auth-Cookie"
COOKIE = "sw_refresh"
COOKIE_PATH = "/auth"  # sent to /auth/refresh and /auth/logout only


def _wants_cookie(request: Request) -> bool:
    return request.headers.get(COOKIE_HEADER) == "1"


def _set_cookie(response: Response, raw: str) -> None:
    s = get_settings()
    response.set_cookie(COOKIE, raw, max_age=s.refresh_token_days * 86400, path=COOKIE_PATH,
                        httponly=True, secure=s.refresh_cookie_secure, samesite="lax")


def _clear_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, secure=s.refresh_cookie_secure, samesite="lax")


def _session(db: Session, user: User, request: Request, response: Response, refresh: str | None = None) -> AuthOut:
    """A new access token, plus a new refresh token (from a fresh family unless `refresh` is the rotated one)."""
    if refresh is None:
        refresh, _ = tokens.issue_refresh(db, user, device_label=request.headers.get("user-agent", ""))
        db.commit()
    if _wants_cookie(request):
        _set_cookie(response, refresh)
        refresh = None
    return AuthOut(access=create_access_token(user), refresh=refresh, user=UserOut.model_validate(user))


def _send_verification(background: BackgroundTasks, db: Session, user: User) -> None:
    raw = tokens.issue_email_token(db, user, "verify_email")
    db.commit()
    link, app_link = email.links("verify", raw)
    # After the response: the provider's latency stays out of the request.
    background.add_task(email.send, "verify_email", user.email, {"link": link, "app_link": app_link, "name": user.name},
                        user.locale)


@router.post("/register", response_model=AuthOut, status_code=201)
@limiter.limit("10/hour")
def register(request: Request, response: Response, body: RegisterIn, background: BackgroundTasks,
             db: Session = Depends(get_db)):
    user = profile.create_user(db, body.email, body.password, body.name, body.locale)
    _send_verification(background, db, user)
    return _session(db, user, request, response)


@router.post("/login", response_model=AuthOut)
@limiter.limit("20/15minutes")
def login(request: Request, response: Response, body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok or user.is_demo:
        raise HTTPException(401, detail={"code": "invalid_credentials"})
    return _session(db, user, request, response)


@router.post("/demo", response_model=AuthOut, status_code=201)
@limiter.limit(lambda: get_settings().demo_limit)
def demo(request: Request, response: Response, body: DemoIn, db: Session = Depends(get_db)):
    """A fresh, private demo account with a sample wardrobe; deleted after DEMO_TTL_HOURS."""
    cleanup_expired_demos(db)
    user = create_demo_user(db, body.locale)
    return _session(db, user, request, response)


@router.post("/refresh", response_model=AuthOut)
@limiter.limit(lambda: get_settings().refresh_limit)
def refresh(request: Request, response: Response, body: RefreshIn | None = None, db: Session = Depends(get_db)):
    """Single use: the old refresh token is spent and a new pair comes back. A spent token presented
    again revokes the whole session family (401 refresh_reused)."""
    raw = (body.refresh if body else None) or request.cookies.get(COOKIE)
    if not raw:
        raise HTTPException(401, detail={"code": "invalid_refresh"})
    user, new_raw = tokens.rotate(db, raw)
    return _session(db, user, request, response, refresh=new_raw)


@router.post("/logout", status_code=204)
def logout(request: Request, body: RefreshIn | None = None, db: Session = Depends(get_db)):
    """This device: its refresh token is revoked (the access token dies within 15 minutes)."""
    raw = (body.refresh if body else None) or request.cookies.get(COOKIE)
    if raw:
        tokens.revoke(db, raw)
    response = Response(status_code=204)
    _clear_cookie(response)
    return response


@router.post("/logout-all", status_code=204)
def logout_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Every device: all refresh tokens revoked and token_version++, so live access tokens stop too."""
    tokens.revoke_all(db, user)
    db.commit()
    response = Response(status_code=204)
    _clear_cookie(response)
    return response


@router.post("/verify", response_model=UserOut)
@limiter.limit(lambda: get_settings().verify_limit)
def verify(request: Request, body: TokenIn, db: Session = Depends(get_db)):
    """The link from the verification email (no sign-in needed: it may open on another device)."""
    user = tokens.use_email_token(db, body.token, "verify_email")
    profile.mark_verified(user)
    db.commit()
    return user


@router.post("/resend-verification", status_code=204)
@limiter.limit(lambda: get_settings().resend_verification_limit)
def resend_verification(request: Request, background: BackgroundTasks, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    if user.email_verified_at is None and not user.is_demo:
        _send_verification(background, db, user)
    return Response(status_code=204)


@router.post("/forgot", status_code=200)
@limiter.limit(lambda: get_settings().forgot_limit)
def forgot(request: Request, body: ForgotIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Always the same answer, whether or not the email has an account (no enumeration)."""
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is not None and not user.is_demo:
        raw = tokens.issue_email_token(db, user, "reset_password")
        db.commit()
        link, app_link = email.links("reset", raw)
        background.add_task(email.send, "reset_password", user.email,
                            {"link": link, "app_link": app_link, "name": user.name}, user.locale)
    return {"status": "ok"}


@router.post("/reset", status_code=204)
@limiter.limit(lambda: get_settings().reset_limit)
def reset(request: Request, body: ResetIn, db: Session = Depends(get_db)):
    """New password; every session and access token is revoked. The link proves the email, too."""
    user = tokens.use_email_token(db, body.token, "reset_password")
    profile.set_password(user, body.password)
    profile.mark_verified(user)
    tokens.revoke_all(db, user)
    db.commit()
    response = Response(status_code=204)
    _clear_cookie(response)
    return response
