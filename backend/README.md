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

## Sign-in sessions and email

Access tokens are 15-minute JWTs carrying `tv` = `users.token_version`; a token whose `tv` is stale gets 401, so bumping the version (logout-all, password reset) signs every device out at once. Refresh tokens are 30 days, single use and stored only as sha256 in `refresh_tokens`; each refresh returns a new one in the same family. A spent token presented again revokes the family (`refresh_reused`), except within 20 s of its rotation, which is two tabs racing (`refresh_superseded`, nothing issued). Mobile keeps the refresh token in SecureStore; the web app sends `X-Auth-Cookie: 1` and gets it as an httpOnly, Secure, SameSite=Lax cookie on `/auth` instead (the API at `api.fomertech.com` is same-site with `wardrobe.fomertech.com`), so `CORS_ORIGINS` is required outside local SQLite and credentials are allowed.

New accounts get a verification email (Resend, `RESEND_API_KEY`, sender `EMAIL_FROM`; links to `APP_URL/auth/verify?token=…` plus the `smartwardrobe://` deep link). Until it is confirmed the account runs on the small `unverified` plan (design doc C3 (a′)): 5 pieces, 3 AI requests a day, tagging + suggestions only — enough to add the first pieces and see a first outfit; confirming the email moves it to `free`. Demo accounts have their own plan. Without `RESEND_API_KEY` emails go to the fake backend (`services.email.OUTBOX`; the link is logged only with SQLite).

## Photo storage

`STORAGE_BACKEND=local` keeps photos as files under `LOCAL_STORAGE_DIR` (default `./data/images`, git-ignored; local runs, tests). Production uses `s3`: the private R2 bucket `smartwardrobe-media`, nothing public. Every response carries a fresh presigned GET link (`image_url`, 15 min, `IMAGE_URL_SECONDS`) plus the stable `image_key` the app caches on; objects are stored with `Cache-Control: private, max-age=900`.

- Each photo has a `wardrobe_images` row: written by `/items/analyze` with `attached_at` NULL, attached (`item_id`, `attached_at`) by `POST /items` — which accepts only a key this user uploaded and that is not on an item yet. Deleting an item deletes the row first and the object after; if the bucket refuses, the row is kept as an orphan (`attached_at` NULL) for the cleanup.
- Demo accounts share 17 pictures under `demo/{file}.webp` (`user_id` NULL), uploaded once on the first `/auth/demo`; they are never deleted. `services.images.copy_shared_image` gives an item its own copy (demo claim, AI-07).
- Account deletion: rows in one transaction, then the `u/{user}/` prefix in the bucket.
- `GET /images/{key}` exists only in local mode, for the signed-in owner (shared demo pictures: demo accounts); 404 otherwise, and always 404 in s3 mode.
- `python scripts/cleanup_orphans.py [--dry-run]` (weekly — `.github/workflows/cleanup.yml` runs it Mondays 03:17 UTC against production once its secrets are set; until then by hand): orphan rows older than 24 h → object + row deleted; stale unverified accounts (> 14 days unused) deleted; `ai_requests` older than 90 days lose their `subject_id` (§9 retention; the rows stay as anonymous aggregates — the 13-month roll-up is a later step); in s3 mode also bucket ↔ table reconciliation (objects with no row and no item, older than 24 h, are deleted; rows whose object is missing are listed).
- Uptime: nothing in the Space tells you it is down. Point an external monitor (UptimeRobot's free plan, 5-minute checks) at `https://api.fomertech.com/` (the health route) and have it e-mail you.

### History: the move to the bucket

Production photos lived in Postgres (`images` table) until 22 Oct 2026, when `scripts/migrate_images_to_r2.py` copied the 73 objects to R2 and `--verify` passed; `STORAGE_BACKEND=s3` has been live since. `0004_cleanup` (AI-09c) then dropped the `images` table and `outfits.item_ids` — it refuses to run while an item has no `wardrobe_images` row — and the migration script was retired (`git log -- backend/scripts/migrate_images_to_r2.py` has it). There is no `db` storage mode any more; `STORAGE_BACKEND=db` is read as `local`.

## Endpoints

| Method | Path | |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | email + password → `{access, refresh, user}`; register also emails a verification link. Register with `claim_demo_token` (a demo account's access token) moves that demo's style profile to the new account and deletes the demo; with `keep_demo_items: true` its 17 pieces (own picture copies), outfits and likes come too — the response's `claimed` says what moved. A bad or spent token is 400 `invalid_demo_token` and creates nothing |
| POST | `/auth/refresh` | `{refresh}` (web: the `sw_refresh` cookie) → a new pair; the old refresh token is spent, and reusing a spent one revokes its whole family |
| POST | `/auth/logout`, `/auth/logout-all` | this device / every device (`token_version++`, all refresh tokens revoked) |
| POST | `/auth/verify`, `/auth/resend-verification` | `{token}` from the email / a new link (5 an hour) |
| POST | `/auth/forgot`, `/auth/reset` | `{email}` → always 200 / `{token, password}` → new password, every session signed out |
| POST | `/auth/demo` | `{locale, style_profile?}` → private demo account with a 17-piece sample wardrobe (deleted after 24 h); `style_profile` carries the onboarding answers (same shape as `PATCH /me/style`) so the first suggestion already uses them |
| GET/PATCH/DELETE | `/me` | profile, city, language; DELETE removes the account and every photo |
| GET | `/me/export` | the account's data as one JSON file (account, style answers, pieces with short-lived photo links, outfits, feedback); 5/hour |
| GET | `/me/entitlements` | plan, limits, features and today's usage (`requests_used/left`, `tokens_used/left`, `reset_at`), plus `after_verify` (what confirming the e-mail unlocks) while unverified — the numbers the app shows, from config |
| GET/PATCH | `/me/style` | style preferences `{answers: {q1 style, q2 palettes, q3 priority}, liked_colors, disliked_colors, styles, avoid}` (fixed vocabularies) + the rule-based taste summary |
| POST | `/items/analyze` | upload a photo → stored + AI-suggested tags, plus `confidence` (0-1) and `uncertain` (tag fields the model flagged) |
| GET/POST | `/items` | list / save (after the user confirms the tags) |
| PATCH/DELETE | `/items/{id}` | edit / delete |
| GET | `/items/analysis` | what the wardrobe is missing: `{season, items, per_category, outfits_possible, neutral_share, gaps: [{code, category?, occasion?, season?, severity, item_ids}]}` — deterministic, no AI request, every plan (`?lat=` picks the hemisphere). Codes: `missing_category`, `occasion_uncovered`, `season_uncovered`, `few_shoes`, `low_neutrals`, `orphan_items`, `few_partners` (a piece with only one thing to wear it with) |
| POST | `/outfits/suggest` | `{occasion, note?, request?, lat?, lon?, lang}` → 2-3 outfits from the user's own items; `request` is free text ("warm smart look, no dress"), parsed first by the intent feature (one extra AI request, so it needs two requests left on the day) — its occasion wins and the answer echoes it as `intent` |
| POST | `/outfits/intent` | `{text, lang}` → `{occasion?, include_categories, include_colors, avoid_categories, avoid_colors, avoid_patterns, wants_outerwear?, brief}`: the same parse on its own, so the app can show what it understood (`intent` feature) |
| POST | `/outfits/capsule` | `{occasions, size 6-20, lang, explain, lat?}` → a capsule chosen deterministically from the user's own pieces for those occasions and the current season (`items, outfits_possible, sample_outfits, gaps`) plus, with `explain`, the model's `summary` and `tips` (one AI request; `capsule` feature, premium) |
| GET | `/outfits` | history (`?liked_only=true`); every outfit carries `source` (`ai` / `ai_edited` / `user`) and `worn_at` |
| POST | `/outfits` | a user-built outfit `{item_ids, occasion, title?}`: own items only, one per category (accessories aside), top + bottom or a dress (`user_outfits` feature) |
| PATCH | `/outfits/{id}/items` | change an outfit's pieces `{item_ids}`; an AI suggestion becomes `ai_edited` (`user_outfits` feature) |
| POST | `/outfits/{id}/worn` | "wore it today": `worn_at`, each piece's `wear_count` / `last_worn_at`; counted once per day |
| POST | `/outfits/{id}/feedback` | `{rating: -1 \| 0 \| 1}` — used in future suggestions |
| GET | `/meta/vocab` | categories, colours, patterns, seasons, occasions, styles, palettes, priorities (no auth) |
| GET | `/weather`, `/cities` | Open-Meteo weather and city search |
| GET | `/images/{key}` | photos in database storage mode, owner only (closed in s3 mode: `image_url` is a presigned link) |

Errors use `{"detail": {"code": "..."}}` so the app can show translated messages.

## Behind a proxy

Rate limits for anonymous endpoints (`/auth/register`, `/auth/login`, `/auth/demo`) are keyed by client IP. The app reads the real IP from `X-Forwarded-For` **only** when the connection comes from a host in `TRUSTED_PROXY_HOSTS` (comma-separated IPs or CIDRs):

- Default `127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16` — local runs and the Hugging Face Space load balancer, which connects from a private address.
- Empty — loopback only.
- Never `*`: any caller could then send a fake `X-Forwarded-For` and get a fresh rate-limit bucket on every request.

- `CLOUDFLARE_PROXY=true` — also trust Cloudflare's published edge ranges, for requests that come through the `api.fomertech.com` Worker (`infra/cloudflare-worker/`). The Worker sets `X-Forwarded-For` to the visitor's IP and the Space's load balancer appends the Worker's Cloudflare egress IP, so without this every visitor shares that one IP. The ranges live in `app/cloudflare_ips.txt`, copied from Cloudflare's official lists <https://www.cloudflare.com/ips-v4> and <https://www.cloudflare.com/ips-v6> (also at <https://www.cloudflare.com/ips/>); refresh with `python scripts/update_cloudflare_ips.py` and commit. A direct caller faking the header still gets its real IP: the load balancer appends it last, and it isn't in any trusted range. Caveat: any Cloudflare Worker, not only ours, connects from these ranges, so someone could run their own Worker against the hf.space URL with a made-up `X-Forwarded-For`; that costs them a Worker per bypass attempt, and the per-user limits on the AI endpoints are not IP-based.

uvicorn's own proxy handling is turned off in the `Dockerfile` (`--no-proxy-headers`) so this setting is the single place that decides. If the host changes, check the address the proxy connects from (`request.client.host` without the middleware) and set the variable.

Other limits: `MAX_UPLOAD_MB` (default 10), the hourly `ANALYZE_LIMIT` / `SUGGEST_LIMIT` / `DEMO_LIMIT`; plan limits are under "Plans and limits" below.

## Error tracking (Sentry)

Off unless `SENTRY_DSN` is set (`app/observability.py`). Only unexpected errors are reported — unhandled exceptions and 5xx `AIError`s (`prompt_not_found`, every provider down) — with the route and the pseudonymous user id. Nothing else about the person travels: no request bodies, query strings (coordinates), credentials, e-mail addresses or IPs (`send_default_pii=False`, `max_request_body_size="never"`, `include_local_variables=False` — frame locals would hold the ASGI scope and request models — `_before_send`, `_before_breadcrumb`, and the `uvicorn.access` log is not turned into breadcrumbs). Expected API errors (4xx, rate limits, 4xx `AIError`s) are the product working and are not sent. Performance tracing is off. `tests/test_observability.py` runs the app against a fake transport and asserts all of this.

Setup: sentry.io → create a project of type *FastAPI* → copy its DSN into the Space secret `SENTRY_DSN` (the app has its own project and DSN, see `app/README.md`).

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
