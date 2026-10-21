"""AI summary from ai_requests / ai_request_attempts: cost, tokens and latency by feature,
fallback / error / budget rates, failures by provider, and how the budget's input estimate compares
with the real input tokens. Plus onboarding: time to first outfit (sign-up → first AI outfit) and
unverified → verified conversion for the accounts registered in the period. Read-only.

    python scripts/ai_report.py                          # yesterday (UTC)
    python scripts/ai_report.py --date 2026-10-19
    python scripts/ai_report.py --days 7                 # the 7 days up to yesterday (weekly)
"""

import argparse
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import AIRequest, AIRequestAttempt, Outfit, User  # noqa: E402


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "-"


def _p(values: list[int], q: float) -> int:
    if not values:
        return 0
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def report(conn: sa.Connection, day: date, days: int = 1) -> str:
    """Covers [day, day + days)."""
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=days)
    reqs = conn.execute(sa.select(AIRequest.__table__).where(AIRequest.created_at >= start,
                                                             AIRequest.created_at < end)).all()
    atts = conn.execute(
        sa.select(AIRequestAttempt.__table__)
        .join(AIRequest.__table__, AIRequestAttempt.request_id == AIRequest.id)
        .where(AIRequest.created_at >= start, AIRequest.created_at < end)
    ).all()

    period = day.isoformat() if days == 1 else f"{day.isoformat()} – {(day + timedelta(days=days - 1)).isoformat()}"
    lines = [f"AI report for {period} (UTC)", ""]
    onboarding = onboarding_lines(conn, start, end)
    if not reqs:
        return "\n".join(lines + ["No AI requests.", "", *onboarding])

    statuses = Counter(r.status for r in reqs)
    cost = sum(r.cost_usd_micro_total for r in reqs) / 1_000_000
    users = len({r.subject_id for r in reqs if r.subject_id})
    lines += [
        f"requests {len(reqs)} · users {users} · cost ${cost:.4f}",
        f"ok {statuses['ok']} · fallback {statuses['fallback']} ({_pct(statuses['fallback'], len(reqs))})"
        f" · error {statuses['error']} ({_pct(statuses['error'], len(reqs))})"
        f" · budget {statuses['budget']} ({_pct(statuses['budget'], len(reqs))})",
        "",
        f"{'feature':<16}{'requests':>9}{'cost $':>10}{'in tok':>10}{'out tok':>10}{'p50 ms':>9}{'p95 ms':>9}",
    ]
    by_feature = defaultdict(list)
    for r in reqs:
        by_feature[r.feature].append(r)
    for feature, rows in sorted(by_feature.items()):
        lat = [r.latency_ms_total for r in rows if r.status in ("ok", "fallback")]
        lines.append(
            f"{feature:<16}{len(rows):>9}{sum(r.cost_usd_micro_total for r in rows) / 1e6:>10.4f}"
            f"{sum(r.input_tokens_total for r in rows):>10}{sum(r.output_tokens_total for r in rows):>10}"
            f"{_p(lat, 0.5):>9}{_p(lat, 0.95):>9}"
        )

    lines += ["", "input tokens: real / budget estimate (answered requests with an estimate):"]
    for feature, rows in sorted(by_feature.items()):
        est = [r for r in rows if r.estimated_input_tokens and r.status in ("ok", "fallback")]
        if est:
            ratio = sum(r.input_tokens_total for r in est) / sum(r.estimated_input_tokens for r in est)
            lines.append(f"  {feature}: {ratio:.2f} over {len(est)} requests "
                         f"(< 1: estimate too high; > 1: too low, raise TEXT_TOKEN_FACTOR)")
        else:
            lines.append(f"  {feature}: -")

    lines += ["", "attempts by model:"]
    by_model = defaultdict(Counter)
    for a in atts:
        by_model[(a.provider, a.model)][a.status] += 1
    for (provider, model), counts in sorted(by_model.items()):
        total = sum(counts.values())
        detail = ", ".join(f"{s} {n}" for s, n in sorted(counts.items()))
        lines.append(f"  {provider}/{model}: {total} ({detail}); failure rate {_pct(total - counts['ok'], total)}")

    errors = Counter(a.error_code for a in atts if a.status != "ok")
    if errors:
        lines += ["", "failure codes: " + ", ".join(f"{c} {n}" for c, n in errors.most_common())]
    if lat_all := [r.latency_ms_total for r in reqs if r.status in ("ok", "fallback")]:
        lines += ["", f"mean latency {statistics.mean(lat_all):.0f} ms"]
    lines += ["", *onboarding]
    return "\n".join(lines)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def onboarding_lines(conn: sa.Connection, start: datetime, end: datetime) -> list[str]:
    """Accounts registered in the period: how many saw a first AI outfit and how fast (median / p90
    seconds from sign-up), how many confirmed their email (C3 (a′): the unverified → verified
    conversion). Demo accounts are left out; the clock starts at users.created_at."""
    users = conn.execute(
        sa.select(User.id, User.created_at, User.email_verified_at)
        .where(User.created_at >= start, User.created_at < end, User.is_demo.is_(False))
    ).all()
    lines = [f"onboarding: {len(users)} accounts registered"]
    if not users:
        return lines
    ids = [u.id for u in users]
    # AI outfits only (an edited suggestion still counts); outfits older than the account are the ones a
    # claimed demo brought along and don't count as the account's first.
    first = dict(
        conn.execute(
            sa.select(Outfit.user_id, sa.func.min(Outfit.created_at))
            .join(User, User.id == Outfit.user_id)
            .where(Outfit.user_id.in_(ids), Outfit.source.in_(("ai", "ai_edited")), Outfit.created_at >= User.created_at)
            .group_by(Outfit.user_id)
        ).all()
    )
    ttfo = [int((_aware(first[u.id]) - _aware(u.created_at)).total_seconds()) for u in users if u.id in first]
    verified = sum(1 for u in users if u.email_verified_at is not None)
    verified_after_outfit = sum(
        1 for u in users if u.email_verified_at is not None and u.id in first and _aware(u.email_verified_at) >= _aware(first[u.id])
    )
    lines.append(f"  first outfit: {len(ttfo)} ({_pct(len(ttfo), len(users))})"
                 + (f" · time to first outfit p50 {_p(ttfo, 0.5)} s · p90 {_p(ttfo, 0.9)} s" if ttfo else ""))
    lines.append(f"  verified: {verified} ({_pct(verified, len(users))}) · of which after seeing an outfit "
                 f"{verified_after_outfit}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--date", type=date.fromisoformat, help="last day of the period (default: yesterday)",
                        default=datetime.now(timezone.utc).date() - timedelta(days=1))
    parser.add_argument("--days", type=int, default=1, help="period length in days, e.g. 7 for a weekly report")
    args = parser.parse_args()

    from app.db import engine

    with engine.connect() as conn:
        print(report(conn, args.date - timedelta(days=args.days - 1), args.days))


if __name__ == "__main__":
    main()
