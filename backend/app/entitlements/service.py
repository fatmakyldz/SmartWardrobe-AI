"""Plans and limits. Routers ask entitlements(user, db) and look at the result; they never name a plan.

Three layers (docs/AI-00-foundation.md §7): the user's base plan → an active subscription's plan →
active entitlement_grants. Several plan sources: the most generous value wins, field by field.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..ai.errors import AIError
from ..models import EntitlementGrant, Subscription, UsageCounter, User

PLANS_FILE = Path(__file__).with_name("plans.default.json")
TIER_RANK = {"standard": 0, "premium": 1}
ACTIVE_SUBSCRIPTION = ("active", "trialing")


@dataclass(frozen=True)
class Entitlements:
    plan: str
    max_items: int
    daily_ai_requests: int  # successful requests/day across request_counted_features
    daily_ai_tokens: int  # billed tokens/day across all AI features
    allowed_features: frozenset[str]
    model_tier: str
    history_limit: int


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    remaining_requests: int | None  # None when the feature isn't request-counted
    remaining_tokens: int
    reset_at: str  # ISO 8601, UTC: the next midnight in the user's timezone


@lru_cache
def plans_config() -> dict:
    return json.loads(PLANS_FILE.read_text())


def _from_plan(name: str) -> Entitlements:
    p = plans_config()["plans"][name]
    return Entitlements(plan=name, max_items=p["max_items"], daily_ai_requests=p["daily_ai_requests"],
                        daily_ai_tokens=p["daily_ai_tokens"], allowed_features=frozenset(p["features"]),
                        model_tier=p["model_tier"], history_limit=p["history_limit"])


def _most_generous(a: Entitlements, b: Entitlements) -> Entitlements:
    better = a if a.plan == b.plan else (a if _rank(a) >= _rank(b) else b)
    return Entitlements(
        plan=better.plan,
        max_items=max(a.max_items, b.max_items),
        daily_ai_requests=max(a.daily_ai_requests, b.daily_ai_requests),
        daily_ai_tokens=max(a.daily_ai_tokens, b.daily_ai_tokens),
        allowed_features=a.allowed_features | b.allowed_features,
        model_tier=max(a.model_tier, b.model_tier, key=lambda t: TIER_RANK.get(t, 0)),
        history_limit=max(a.history_limit, b.history_limit),
    )


def _rank(e: Entitlements) -> tuple:
    return (TIER_RANK.get(e.model_tier, 0), e.max_items, e.daily_ai_requests)


def entitlements(user: User, db: Session, now: datetime | None = None) -> Entitlements:
    """Read-only: never writes, never changes subscription state."""
    now = now or datetime.now(timezone.utc)
    plans = plans_config()["plans"]

    base = "demo" if user.is_demo else (user.plan if user.plan in plans else "free")
    ent = _from_plan(base)
    if user.is_demo:
        return ent  # demo accounts get no subscriptions or grants
    if user.email_verified_at is None:
        # C3 (a′): until the email is confirmed the account runs on the small `unverified` plan — enough
        # to tag the first pieces and see a first outfit, nothing more. Subscriptions and grants wait.
        return _from_plan("unverified")

    sub = db.scalars(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status.in_(ACTIVE_SUBSCRIPTION),
            or_(Subscription.current_period_end.is_(None), Subscription.current_period_end > now),
        )
        .order_by(Subscription.created_at.desc())
    ).first()
    if sub and sub.plan in plans:
        ent = _most_generous(ent, _from_plan(sub.plan))

    grants = db.scalars(
        select(EntitlementGrant).where(
            EntitlementGrant.user_id == user.id,
            EntitlementGrant.starts_at <= now,
            or_(EntitlementGrant.ends_at.is_(None), EntitlementGrant.ends_at > now),
        )
    ).all()
    for g in grants:
        if g.plan_override in plans:
            ent = _most_generous(ent, _from_plan(g.plan_override))
        if g.feature:
            ent = Entitlements(**{**ent.__dict__, "allowed_features": ent.allowed_features | {g.feature}})
        if isinstance(g.limits, dict):
            fields = {k: v for k, v in g.limits.items() if k in ("max_items", "daily_ai_requests", "daily_ai_tokens",
                                                                  "history_limit") and isinstance(v, int)}
            ent = Entitlements(**{**ent.__dict__, **{k: max(getattr(ent, k), v) for k, v in fields.items()}})
    return ent


def require_feature(ent: Entitlements, feature: str) -> None:
    if feature not in ent.allowed_features:
        raise AIError("feature_not_allowed", feature=feature)


# ── daily AI budget ──────────────────────────────────────────────────────

def _zone(tz_name: str | None):
    try:
        return ZoneInfo(tz_name) if tz_name else timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def period_start(tz_name: str | None, now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(_zone(tz_name)).date()


def reset_at(tz_name: str | None, now: datetime | None = None) -> str:
    zone = _zone(tz_name)
    day = period_start(tz_name, now)
    midnight = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return midnight.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def request_counted(feature: str) -> bool:
    return feature in plans_config()["request_counted_features"]


def check_ai_budget(db: Session, subject_id: uuid.UUID, feature: str, est_tokens: int, ent: Entitlements,
                    tz_name: str | None = None, now: datetime | None = None) -> BudgetDecision:
    day = period_start(tz_name, now)
    rows = db.execute(
        select(UsageCounter.feature, func.coalesce(UsageCounter.count, 0), func.coalesce(UsageCounter.tokens, 0))
        .where(UsageCounter.user_id == subject_id, UsageCounter.period_start == day)
    ).all()
    tokens_used = sum(r[2] for r in rows)
    counted = [r[1] for r in rows if request_counted(r[0])]
    remaining_tokens = max(0, ent.daily_ai_tokens - tokens_used)
    remaining_requests = max(0, ent.daily_ai_requests - sum(counted)) if request_counted(feature) else None

    allowed = tokens_used + est_tokens <= ent.daily_ai_tokens and remaining_requests != 0
    return BudgetDecision(allowed=allowed, remaining_requests=remaining_requests, remaining_tokens=remaining_tokens,
                          reset_at=reset_at(tz_name, now))


def consume(db: Session, subject_id: uuid.UUID, feature: str, tokens: int, requests: int = 0,
            tz_name: str | None = None, now: datetime | None = None) -> None:
    """UPSERT today's usage_counters row. Caller commits."""
    if not tokens and not requests:
        return
    values = {"user_id": subject_id, "feature": feature, "period_start": period_start(tz_name, now),
              "count": requests, "tokens": tokens}
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    stmt = insert(UsageCounter).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "feature", "period_start"],
        set_={"count": UsageCounter.count + stmt.excluded.count, "tokens": UsageCounter.tokens + stmt.excluded.tokens},
    )
    db.execute(stmt)


class UserBudget:
    """The BudgetGate the gateway talks to. Holds limits and a session factory, not the caller's session."""

    def __init__(self, user: User, ent: Entitlements, session_factory=None):
        if session_factory is None:
            from ..db import SessionLocal

            session_factory = SessionLocal
        self.subject_id = user.id
        self.tz_name = user.timezone
        self.ent = ent
        self._sessions = session_factory

    def check(self, feature: str, estimated_tokens: int) -> BudgetDecision:
        with self._sessions() as db:
            return check_ai_budget(db, self.subject_id, feature, estimated_tokens, self.ent, self.tz_name)

    def consume(self, feature: str, tokens: int, succeeded: bool = False) -> None:
        requests = 1 if succeeded and request_counted(feature) else 0
        with self._sessions() as db:
            consume(db, self.subject_id, feature, tokens, requests, self.tz_name)
            db.commit()
