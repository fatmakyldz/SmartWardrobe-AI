# Deferred revisions

Written ahead of time, **not applied**: alembic only reads `migrations/versions/`, and the Space runs
`alembic upgrade head` on every start, so a file here can't run by accident.

| File | Applies in | Before moving it to `versions/` |
|---|---|---|
| `0004_cleanup.py` | AI-09 (§14 C9) | R2 migration verified (`scripts/migrate_images_to_r2.py --verify` OK) and `STORAGE_BACKEND=s3` live for ≥ 1 week; a Neon backup/branch taken; in the same PR remove `StoredImage`, `DbStorage`'s use of it and `Outfit.item_ids` (plus the `item_ids` fallbacks in `serialize.py` / `services/profile.py`), so `alembic check` stays clean. Irreversible: the downgrade restores the columns, not the data. |
