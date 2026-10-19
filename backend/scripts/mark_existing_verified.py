"""Pre-launch accounts → email verified (stop condition C1, docs/AI-00-foundation.md §14).

After 0002_ai_foundation every account has email_verified_at = NULL. Once AI features require a
verified email (AI-05), accounts created before verification existed would be locked out. This marks
them verified with email_verified_at = created_at. Demo accounts are skipped (they are exempt anyway).

Run after `alembic upgrade head`, against the database in DATABASE_URL:

    python scripts/mark_existing_verified.py           # dry run: counts only
    python scripts/mark_existing_verified.py --apply   # writes

Safe to run more than once: only rows that are still unverified are touched.
"""

import argparse
import sys
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import User  # noqa: E402

users = User.__table__
_unverified = sa.and_(users.c.email_verified_at.is_(None), users.c.is_demo.is_(False))


def run(conn: sa.Connection, apply: bool) -> dict[str, int]:
    counts = {
        "users": conn.scalar(sa.select(sa.func.count()).select_from(users)),
        "demo": conn.scalar(sa.select(sa.func.count()).select_from(users).where(users.c.is_demo.is_(True))),
        "to_mark": conn.scalar(sa.select(sa.func.count()).select_from(users).where(_unverified)),
    }
    if apply and counts["to_mark"]:
        conn.execute(sa.update(users).where(_unverified).values(email_verified_at=users.c.created_at))
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    args = parser.parse_args()

    from app.db import engine

    with engine.begin() as conn:
        c = run(conn, args.apply)
    print(f"users: {c['users']} (demo: {c['demo']}), unverified non-demo: {c['to_mark']}")
    print(f"marked {c['to_mark']} as verified" if args.apply else "dry run — nothing written; add --apply")


if __name__ == "__main__":
    main()
