"""Delete photos that never made it onto an item, and reconcile the bucket with wardrobe_images (§8).

1. Orphans: rows with attached_at NULL older than 24 h (an analyze the user never saved, or a delete
   whose bucket call failed) → object and row deleted.
2. Stale unverified accounts: never confirmed the email and not used for 14 days → account and photos
   deleted, like expired demo accounts (C3 (a′)).
3. Reconciliation, both ways (STORAGE_BACKEND=s3 only): objects in the bucket with no row and no item
   pointing at them, older than 24 h → deleted; rows whose object is missing → listed (not fixable
   here: the photo is gone). Shared demo pictures (demo/…) are never deleted.

Uses the configured storage (STORAGE_BACKEND, S3_*) and DATABASE_URL. Weekly, by hand or a cron job:

    python scripts/cleanup_orphans.py --dry-run
    python scripts/cleanup_orphans.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.services.images import cleanup_orphans, reconcile  # noqa: E402
from app.services.profile import cleanup_stale_unverified  # noqa: E402


def _show(label: str, keys: list[str], limit: int = 20) -> None:
    print(f"{label}: {len(keys)}")
    for k in keys[:limit]:
        print(f"  {k}")
    if len(keys) > limit:
        print(f"  … {len(keys) - limit} more")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="list only; delete nothing")
    args = parser.parse_args()

    from app.db import SessionLocal

    verb = "would delete" if args.dry_run else "deleted"
    with SessionLocal() as db:
        r = cleanup_orphans(db, dry_run=args.dry_run)
        _show(f"orphan rows (>24 h, {verb})", r.orphan_rows)
        _show("failed", r.failed)
        _show(f"stale unverified accounts (>14 days unused, {verb})", cleanup_stale_unverified(db, dry_run=args.dry_run))
        if get_settings().storage_backend != "s3":
            print("reconciliation skipped: STORAGE_BACKEND is not s3")
            return
        r = reconcile(db, dry_run=args.dry_run)
        _show(f"bucket objects without a row (>24 h, {verb})", r.stray_objects)
        _show("rows whose object is missing (not fixed)", r.missing_objects)
        _show("failed", r.failed)


if __name__ == "__main__":
    main()
