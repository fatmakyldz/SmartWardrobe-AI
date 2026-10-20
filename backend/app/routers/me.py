from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..ai import telemetry
from ..db import get_db
from ..models import User
from ..schemas import StyleIn, StyleOut, UserOut, UserUpdate
from ..security import current_user
from ..services import profile

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("", response_model=UserOut)
def update_me(body: UserUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return profile.update_profile(db, user, body.model_dump(exclude_unset=True))


@router.delete("", status_code=204)
def delete_me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Deletes the account, wardrobe, outfits and photos (required by the App Store). Sessions and email
    tokens go by cascade; AI telemetry keeps no link to the person."""
    telemetry.forget_subject(db, user.id)  # same transaction as the account rows
    profile.delete_account(db, user)
    return Response(status_code=204)


def _style_out(user: User) -> StyleOut:
    return StyleOut(**{k: v for k, v in (user.style_profile or {}).items() if k in StyleOut.model_fields},
                    summary=user.style_summary)


@router.get("/style", response_model=StyleOut)
def get_style(user: User = Depends(current_user)):
    return _style_out(user)


@router.patch("/style", response_model=StyleOut)
def update_style(body: StyleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Onboarding answers and explicit preferences (§10 steps 1 and 6). Open to every plan, demo included."""
    profile.update_style(db, user, body.model_dump(exclude_unset=True))
    return _style_out(user)
