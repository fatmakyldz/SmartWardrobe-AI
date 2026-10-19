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
cp .env.example .env            # add ANTHROPIC_API_KEY and/or GROQ_API_KEY
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
2. Clear expired demo accounts so they aren't migrated — **from a checkout of the current `main`** (this branch's models expect the 0002 columns): `python -c "from app.db import SessionLocal; from app.demo import cleanup_expired_demos as c; db = SessionLocal(); print(c(db))"` (deletes up to 50 per run; repeat until it prints 0).
3. Count real accounts: `SELECT count(*) FROM users WHERE NOT is_demo;`
4. Preview the data step (read-only, works on the 0001 schema): `python scripts/preview_0002_data_step.py` — prints how many `outfit_items` / `feedback_events` rows it will write and how many item ids it will skip, by reason: `deleted_item`, `foreign_item` (another user's item), `duplicate_id`, `invalid_id`. The migration logs the same totals.
5. Deploy (merge to `main`) — the container runs the migration.
6. If step 3 found real accounts, mark them verified so they aren't locked out once AI features require a verified email (decision C1):
   ```bash
   python scripts/mark_existing_verified.py           # dry run: prints counts
   python scripts/mark_existing_verified.py --apply   # email_verified_at = created_at (demo accounts skipped)
   ```
   This is deliberately not part of the migration; it is idempotent and can run any time before AI-05 ships.

`wardrobe_images.user_id` is NULL only for shared demo images. Any query that lists images must filter with `WardrobeImage.visible_to(user)`, which includes NULL-owner rows for demo accounts only.

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

Other limits: `MAX_UPLOAD_MB` (default 10), the hourly `ANALYZE_LIMIT` / `SUGGEST_LIMIT` / `DEMO_LIMIT`; plan limits are under "Plans and limits" below.

## How the AI parts work

All model calls go through one gateway (`app/ai/`, design in `docs/AI-00-foundation.md` §3–§5):

```
router → entitlements (plan, feature allowed?) → features/{tagging,suggest} (prompt + schema)
       → gateway: daily budget → model chain → attempts / fallback → schema check → telemetry
       → providers/{anthropic,groq}
```

- **Models** live only in `app/ai/routes.default.json` (override with `AI_ROUTES`): tagging uses Claude Haiku (vision) then Groq Qwen vision; suggestions use Claude Sonnet then Groq `gpt-oss-120b`. Prices there drive the cost in `ai_requests`. A provider without an API key is skipped.
- **Retries and fallback**: a timeout or rate limit is retried once on the same model, an answer that fails the schema is retried once with a "fix the format" note, anything else moves to the next model. A provider failing 5 times in 5 minutes goes to the end of the chain for 2 minutes.
- **Output** is never trusted: Claude must answer through one strict tool, Groq in JSON mode, and every answer is validated and coerced into the fixed vocabularies (`app/ai/schemas/`, `app/vocab.py`). Outfits may only use the user's own item numbers. The LLM never writes to the database.
- **Prompts** are versioned files in `app/ai/prompts/<feature>/v1.md`; outfits store the prompt version and the `ai_requests` id.
- **Telemetry**: one `ai_requests` row per request and one `ai_request_attempts` row per provider call (tokens, cost, latency, status), plus a JSON log line per attempt. Prompts, photos and notes are never logged — only a prompt hash and token counts. `python scripts/ai_report.py [--date YYYY-MM-DD]` prints a day's cost, latency, fallback and error summary.

## Plans and limits

`app/entitlements/plans.default.json` (design §7):

| Plan | Items | AI suggestions / day | AI tokens / day | Features |
|---|---|---|---|---|
| free | 50 | 5 | 40 000 | tagging, suggest |
| premium | 300 | 60 | 600 000 | + capsule (later) |
| demo | 17 (the sample wardrobe) | 5 | 40 000 | suggest only |

- The daily **request** limit counts only successful suggestions (`request_counted_features`); photo tagging is limited by the item count, the hourly rate limit and the token budget.
- The daily **token** budget counts every billed provider call, failed ones included, across all features.
- Days follow the user's timezone (UTC when unset). Over the limit the API answers `429 {"code": "budget_exceeded", "reset_at": …, "remaining": …}`; a feature outside the plan answers `403 feature_not_allowed`.
- A user's plan comes from `users.plan`, an active `subscriptions` row, then active `entitlement_grants` (promo, support, testers); the most generous value wins.
- Both AI endpoints accept an optional `Idempotency-Key` header; the same key within 60 s returns the first answer instead of a second model call. The same photo is tagged once per minute without a key.
