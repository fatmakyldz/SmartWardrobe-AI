"""Daily AI summary from ai_requests / ai_request_attempts: cost, tokens and latency by feature,
fallback / error / budget rates, failures by provider. Read-only.

    python scripts/ai_report.py                  # yesterday (UTC)
    python scripts/ai_report.py --date 2026-10-19
"""

import argparse
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import AIRequest, AIRequestAttempt  # noqa: E402


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "-"


def _p(values: list[int], q: float) -> int:
    if not values:
        return 0
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def report(conn: sa.Connection, day: date) -> str:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    reqs = conn.execute(sa.select(AIRequest.__table__).where(AIRequest.created_at >= start,
                                                             AIRequest.created_at < end)).all()
    atts = conn.execute(
        sa.select(AIRequestAttempt.__table__)
        .join(AIRequest.__table__, AIRequestAttempt.request_id == AIRequest.id)
        .where(AIRequest.created_at >= start, AIRequest.created_at < end)
    ).all()

    lines = [f"AI report for {day.isoformat()} (UTC)", ""]
    if not reqs:
        return "\n".join(lines + ["No AI requests."])

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
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--date", type=date.fromisoformat,
                        default=datetime.now(timezone.utc).date() - timedelta(days=1))
    args = parser.parse_args()

    from app.db import engine

    with engine.connect() as conn:
        print(report(conn, args.date))


if __name__ == "__main__":
    main()
