from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..ai import telemetry
from ..db import get_db
from ..models import User
from ..entitlements import entitlements
from ..entitlements.service import after_verify, usage_snapshot
from ..schemas import AfterVerifyOut, EntitlementsOut, StyleIn, StyleOut, UsageOut, UserOut, UserUpdate
from ..security import current_user
from ..services import profile
from ..services.wardrobe import active_item_count

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


@router.get("/entitlements", response_model=EntitlementsOut)
def my_entitlements(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Plan, limits, features and today's usage (AI-08). Read-only; the gateway's own budget check is the
    one that decides a request, this is the same numbers for the app to show."""
    ent = entitlements(user, db)
    decision = usage_snapshot(db, user, ent)
    used_requests = ent.daily_ai_requests - (decision.remaining_requests or 0)
    nxt = after_verify(user)
    return EntitlementsOut(
        plan=ent.plan, verified=nxt is None,
        after_verify=AfterVerifyOut(plan=nxt.plan, max_items=nxt.max_items, daily_ai_requests=nxt.daily_ai_requests) if nxt else None,
        max_items=ent.max_items, items_used=active_item_count(user),
        daily_ai_requests=ent.daily_ai_requests, daily_ai_tokens=ent.daily_ai_tokens,
        features=sorted(ent.allowed_features), model_tier=ent.model_tier, history_limit=ent.history_limit,
        usage=UsageOut(requests_used=max(0, used_requests), requests_left=decision.remaining_requests or 0,
                       tokens_used=ent.daily_ai_tokens - decision.remaining_tokens, tokens_left=decision.remaining_tokens,
                       reset_at=decision.reset_at),
    )


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
