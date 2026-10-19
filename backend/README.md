---
title: SmartWardrobe API
emoji: 👗
colorFrom: purple
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
---

# SmartWardrobe API

FastAPI backend for [SmartWardrobe](https://github.com/fatmakyldz/SmartWardrobe-AI). The front matter above lets this folder run as a Docker Space on Hugging Face.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # add GROQ_API_KEY
alembic upgrade head            # SQLite by default
uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
pytest
```

## Database migrations

Schema changes are Alembic revisions in `migrations/versions/`. The Docker image runs `alembic upgrade head` on every start, so **a merge to `main` migrates the production database on the next Space deploy**.

```bash
alembic upgrade head            # apply
alembic downgrade -1            # undo the last revision
alembic check                   # models and database agree (CI runs this on Postgres)
alembic revision --autogenerate -m "..."   # new revision; review it before committing
```

Tests run on SQLite by default; set `TEST_DATABASE_URL` to run the same suite on Postgres (a separate variable, so a `DATABASE_URL` you exported for real work is never wiped by the tests):

```bash
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/sw_test pytest -q
```

### Before deploying `0002_ai_foundation`

It adds fields to `users` / `items` / `outfits`, ten new tables, and copies `outfits.item_ids` → `outfit_items` and ratings → `feedback_events` (`outfits.item_ids` and `images` stay until `0003_cleanup`). On the production database (Neon), before the deploy:

1. Take a Neon branch (snapshot) to roll back to.
2. Clear expired demo accounts so they aren't migrated: `python -c "from app.db import SessionLocal; from app.demo import cleanup_expired_demos as c; db = SessionLocal(); print(c(db))"` (deletes up to 50 per run; repeat until it prints 0).
3. Count real accounts: `SELECT count(*) FROM users WHERE NOT is_demo;`
4. Deploy (merge to `main`) — the container runs the migration.
5. If step 3 found real accounts, mark them verified so they aren't locked out once AI features require a verified email (decision C1):
   ```bash
   python scripts/mark_existing_verified.py           # dry run: prints counts
   python scripts/mark_existing_verified.py --apply   # email_verified_at = created_at (demo accounts skipped)
   ```
   This is deliberately not part of the migration; it is idempotent and can run any time before AI-05 ships.

## Endpoints

| Method | Path | |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | email + password → token |
| POST | `/auth/demo` | private demo account with a 17-piece sample wardrobe (deleted after 24 h) |
| GET/PATCH/DELETE | `/me` | profile, city, language; DELETE removes the account and every photo |
| POST | `/items/analyze` | upload a photo → stored + AI-suggested tags |
| GET/POST | `/items` | list / save (after the user confirms the tags) |
| PATCH/DELETE | `/items/{id}` | edit / delete |
| POST | `/outfits/suggest` | `{occasion, note?, lat?, lon?, lang}` → 2-3 outfits from the user's own items |
| GET | `/outfits` | history (`?liked_only=true`) |
| POST | `/outfits/{id}/feedback` | `{rating: -1 \| 0 \| 1}` — used in future suggestions |
| GET | `/weather`, `/cities` | Open-Meteo weather and city search |
| GET | `/images/{key}` | photos (database storage mode) |

Errors use `{"detail": {"code": "..."}}` so the app can show translated messages.

## Behind a proxy

Rate limits for anonymous endpoints (`/auth/register`, `/auth/login`, `/auth/demo`) are keyed by client IP. The app reads the real IP from `X-Forwarded-For` **only** when the connection comes from a host in `TRUSTED_PROXY_HOSTS` (comma-separated IPs or CIDRs):

- Default `127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16` — local runs and the Hugging Face Space load balancer, which connects from a private address.
- Empty — loopback only.
- Never `*`: any caller could then send a fake `X-Forwarded-For` and get a fresh rate-limit bucket on every request.

uvicorn's own proxy handling is turned off in the `Dockerfile` (`--no-proxy-headers`) so this setting is the single place that decides. If the host changes, check the address the proxy connects from (`request.client.host` without the middleware) and set the variable.

Other limits: `MAX_ITEMS` (pieces per wardrobe, default 300), `MAX_UPLOAD_MB` (default 10), `ANALYZE_LIMIT` / `SUGGEST_LIMIT` / `DEMO_LIMIT`.

## How the AI parts work

- **Tagging** — the photo is re-encoded (EXIF/GPS stripped), downscaled, and sent to a Groq vision model (`GROQ_VISION_MODEL`, default `qwen/qwen3.8-27b`) in JSON mode. Every field is coerced into fixed vocabularies (`app/vocab.py`), and the user confirms before saving.
- **Outfits** — the wardrobe is sent as numbered items with their attributes, plus today's weather (Open-Meteo), the occasion and the user's liked/disliked combinations. The text model (`GROQ_TEXT_MODEL`, default `openai/gpt-oss-120b`) answers with item numbers only; the server drops unknown ids, duplicate categories, incomplete or repeated outfits (`app/ai.py`).
