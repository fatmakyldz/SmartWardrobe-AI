"""usage_counters ↔ ai_requests reconciliation (§7): the counters are the fast path the budget reads;
ai_requests is the truth. Once a day the counters for a day are rewritten from ai_requests, and any
drift over DRIFT_WARN is reported. Days are the user's local day (usage_counters.period_start), so
ai_requests rows are bucketed with the user's timezone."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AIRequest, UsageCounter, User
from .service import _zone, request_counted

DRIFT_WARN = 0.01  # 1 %: anything bigger is worth a look (a gateway bug, not a race)
COUNTED_STATUSES = ("ok", "fallback")


@dataclass(frozen=True)
class Drift:
    user_id: uuid.UUID
    feature: str
    counter_count: int
    truth_count: int
    counter_tokens: int
    truth_tokens: int

    @property
    def token_drift(self) -> float:
        base = max(self.truth_tokens, 1)
        return abs(self.counter_tokens - self.truth_tokens) / base

    @property
    def warn(self) -> bool:
        return self.counter_count != self.truth_count or self.token_drift > DRIFT_WARN


def reconcile_day(db: Session, day: date, apply: bool = True) -> list[Drift]:
    """Compare and (with apply) rewrite every (user, feature) counter for `day`. Returns the rows that
    differed. The caller commits."""
    # ai_requests within ±1 day of the UTC day cover every timezone's local `day`.
    start = datetime.combine(day - timedelta(days=1), time.min, tzinfo=timezone.utc)
    end = datetime.combine(day + timedelta(days=2), time.min, tzinfo=timezone.utc)
    rows = db.execute(
        select(AIRequest.subject_id, AIRequest.feature, AIRequest.status, AIRequest.input_tokens_total,
               AIRequest.output_tokens_total, AIRequest.created_at, User.timezone)
        .join(User, User.id == AIRequest.subject_id)
        .where(AIRequest.created_at >= start, AIRequest.created_at < end)
    ).all()

    truth: dict[tuple[uuid.UUID, str], list[int]] = {}
    for subject_id, feature, status, inp, out, created_at, tz_name in rows:
        local_day = (created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)).astimezone(_zone(tz_name)).date()
        if local_day != day:
            continue
        entry = truth.setdefault((subject_id, feature), [0, 0])
        entry[1] += (inp or 0) + (out or 0)  # every billed attempt counts against the token budget
        if status in COUNTED_STATUSES and request_counted(feature):
            entry[0] += 1

    counters = {(c.user_id, c.feature): c for c in db.scalars(select(UsageCounter).where(UsageCounter.period_start == day))}
    drifts: list[Drift] = []
    for key in set(truth) | set(counters):
        t_count, t_tokens = truth.get(key, [0, 0])
        c = counters.get(key)
        c_count, c_tokens = (c.count, c.tokens) if c else (0, 0)
        if (c_count, c_tokens) == (t_count, t_tokens):
            continue
        drifts.append(Drift(key[0], key[1], c_count, t_count, c_tokens, t_tokens))
        if apply:
            if c is None:
                db.add(UsageCounter(user_id=key[0], feature=key[1], period_start=day, count=t_count, tokens=t_tokens))
            else:
                c.count, c.tokens = t_count, t_tokens
    return drifts
