"""Rewrite yesterday's usage_counters from ai_requests (the truth) and report any drift (§7).

    python scripts/reconcile_usage.py             # yesterday (UTC), apply
    python scripts/reconcile_usage.py --dry-run   # report only
    python scripts/reconcile_usage.py --date 2026-10-20
"""

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.entitlements.reconcile import reconcile_day  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--date", type=date.fromisoformat, default=datetime.now(timezone.utc).date() - timedelta(days=1))
    parser.add_argument("--dry-run", action="store_true", help="report only; change nothing")
    args = parser.parse_args()

    from app.db import SessionLocal

    with SessionLocal() as db:
        drifts = reconcile_day(db, args.date, apply=not args.dry_run)
        if not args.dry_run:
            db.commit()
    verb = "would fix" if args.dry_run else "fixed"
    print(f"usage reconciliation for {args.date}: {len(drifts)} counter(s) differed ({verb})")
    for d in drifts:
        flag = "  WARN" if d.warn else ""
        print(f"  {d.user_id} {d.feature}: count {d.counter_count} → {d.truth_count}, "
              f"tokens {d.counter_tokens} → {d.truth_tokens} ({d.token_drift:.1%}){flag}")


if __name__ == "__main__":
    main()
