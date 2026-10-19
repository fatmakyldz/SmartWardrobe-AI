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

It adds fields to `users` / `items` / `outfits`, ten new tables, and copies `outfits.item_ids` → `outfit_items` and ratings → `feedback_events` (`outfits.item_ids` and `images` stay until the cleanup revision — called `0003_cleanup` in the design, now the next free number since `0003_ai_estimate` took 0003). On the production database (Neon), before the deploy:

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
| GET/PATCH | `/me/style` | style preferences `{answers: {q1 style, q2 palettes, q3 priority}, liked_colors, disliked_colors, styles, avoid}` (fixed vocabularies) + the rule-based taste summary |
| POST | `/items/analyze` | upload a photo → stored + AI-suggested tags |
| GET/POST | `/items` | list / save (after the user confirms the tags) |
| PATCH/DELETE | `/items/{id}` | edit / delete |
| POST | `/outfits/suggest` | `{occasion, note?, lat?, lon?, lang}` → 2-3 outfits from the user's own items |
| GET | `/outfits` | history (`?liked_only=true`) |
| POST | `/outfits` | a user-built outfit `{item_ids, occasion, title?}`: own items only, one per category (accessories aside), top + bottom or a dress (`user_outfits` feature) |
| PATCH | `/outfits/{id}/items` | change an outfit's pieces `{item_ids}`; an AI suggestion becomes `ai_edited` (`user_outfits` feature) |
| POST | `/outfits/{id}/worn` | "wore it today": `worn_at`, each piece's `wear_count` / `last_worn_at`; counted once per day |
| POST | `/outfits/{id}/feedback` | `{rating: -1 \| 0 \| 1}` — used in future suggestions |
| GET | `/meta/vocab` | categories, colours, patterns, seasons, occasions, styles, palettes, priorities (no auth) |
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

## Code layout

Routers check auth, input and plan, then call one service. **Services are the only writers of business data** (users, items, outfits, outfit_items, feedback_events); `ai/telemetry` (`ai_requests`) and `entitlements` (`usage_counters`) write only their own tables. Services never call `app.ai`; `services/orchestration.py` reads what a suggestion needs and hands it to `ai/context.py` as plain DTOs.

| Module | |
|---|---|
| `services/wardrobe.py` | photo upload, item list / create / edit / delete |
| `services/outfits.py` | saving suggestions, user outfits, editing pieces, "worn" |
| `services/feedback.py` | 👍 / 👎 → `outfits.rating` + `feedback_events` |
| `services/profile.py` | accounts, profile, style preferences, rule-based taste summary |
| `services/demo.py` | demo accounts |
| `services/orchestration.py` | collects DTOs for `ai.context` (read-only) |
| `ai/context.py` | pure: wardrobe pre-filter, ordering, item numbering, the text the model sees |

### What goes into a suggestion (design §6)

`ai/context.py` builds the context from DTOs and a `today` date — no DB, no clock — so it is snapshot-tested:

1. **Pre-filter**: archived pieces out; pieces whose seasons miss today's season out (southern hemisphere flipped); warmth vs. feels-like (above 24 °C no warmth ≥ 4, below 8 °C no warmth ≤ 1); the occasion's formality window (casual 1–3, work 2–4, formal 4–5, sport 1–2, date 2–4, party 2–5, travel 1–3); caps per category (top 20, bottom 12, dress 8, outerwear 8, shoes 8, bag 5, accessory 8). If what is left can't make an outfit, the season, then warmth, then formality filter is dropped.
2. **Order and numbers**: favourites, then most recently worn, then newest, then id. The model only sees these numbers; `index_to_item_id` maps them back.
3. **Around the wardrobe**: occasion + note (200 chars, e-mails and phone numbers masked), weather + season, style preferences, the taste summary, the last 5 like / dislike / worn events as category + colour, pieces worn in the last 7 days ("prefer variety").

The **taste summary** is not an LLM call: `services/profile.py` turns the last 30 like / dislike / worn events into 3–4 template sentences (colours, pieces, formality, colours to avoid) in the user's language. It is rebuilt after 10 new events or when it is older than 7 days.

Context size: the 17-piece demo wardrobe ≈ 450 tokens; a 300-piece wardrobe ≈ 1 850 (was ≈ 8 000 when the whole wardrobe was sent).

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
- **Prompts** are versioned files in `app/ai/prompts/<feature>/vN.md`; outfits store the prompt version and the `ai_requests` id. Suggestions use `suggest/v2` (same system text as v1, the §6 context).
- **Telemetry**: one `ai_requests` row per request and one `ai_request_attempts` row per provider call (tokens, cost, latency, status), plus a JSON log line per attempt. Prompts, photos and notes are never logged — only a prompt hash and token counts. `python scripts/ai_report.py [--date YYYY-MM-DD] [--days 7]` prints cost, latency, fallback and error rates for a day (or a week), and the real-input / budget-estimate ratio per feature.
- **Budget estimate**: before calling out, the gateway estimates input tokens as text chars / 4 × 2.5 + 600 (tool schema and instructions) + 1 600 per image, and stores it in `ai_requests.estimated_input_tokens`. Only the budget check uses it; the counters always get the real tokens. If the weekly ratio drifts far from 1, adjust `TEXT_TOKEN_FACTOR` / `FIXED_INPUT_TOKENS` in `app/ai/gateway.py`.

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
