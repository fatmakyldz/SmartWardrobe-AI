"""Dry run of the 0002_ai_foundation data step: what item_ids → outfit_items would write and skip.

Read-only; works on a database still at 0001 (run it on production before merging AI-02) or later.

    python scripts/preview_0002_data_step.py

Skip reasons: deleted_item (id no longer in items), foreign_item (item belongs to another user),
duplicate_id (same id twice in one outfit), invalid_id (not a UUID).
"""

import importlib.util
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def load_migration():
    path = BACKEND / "migrations" / "versions" / "0002_ai_foundation.py"
    spec = importlib.util.spec_from_file_location("m0002_ai_foundation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preview(conn) -> dict[str, int]:
    return load_migration().summarize(conn, write=False)


def main() -> None:
    from app.db import engine

    with engine.connect() as conn:
        t = preview(conn)
        conn.rollback()
    rows = [("outfits scanned", t["outfits"]), ("outfit_items to write", t["outfit_items"]),
            ("feedback_events to write", t["feedback_events"])]
    rows += [(f"skipped: {r}", t[r]) for r in ("deleted_item", "foreign_item", "duplicate_id", "invalid_id")]
    for label, value in rows:
        print(f"{label:<28}{value}")
    print("dry run — nothing written")

if __name__ == "__main__":
    main()
