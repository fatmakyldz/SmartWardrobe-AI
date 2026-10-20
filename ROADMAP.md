# SmartWardrobe v2 — roadmap

The 2025 Streamlit graduation project, rebuilt as a real product: a FastAPI backend and one Expo (React Native) app for iOS, Android and the web, in English and Turkish.
The original code is preserved on the [`legacy-streamlit`](https://github.com/fatmakyldz/SmartWardrobe-AI/tree/legacy-streamlit) branch.

## Decisions

| Topic | Choice | Why |
|---|---|---|
| Backend | FastAPI + SQLAlchemy + Alembic | Python, typed, easy to test |
| App | Expo SDK 58 (React Native) + Expo Router | one codebase → iOS, Android, web |
| Look | oyster / paper / aubergine / tailor's-tape yellow, Bricolage Grotesque; outfits shown as a tilted flat-lay board | a fashion app that doesn't look like a template |
| Languages | English + Turkish | `en` / `tr` everywhere, AI answers in the user's language |
| Clothing recognition | Groq vision LLM (`qwen/qwen3.8-27b`) | colour, pattern, season and warmth in one call; replaces the old TensorFlow model |
| Outfit suggestions | Groq `openai/gpt-oss-120b`, picks **only the user's own items** by id | validated server-side, learns from 👍/👎 |
| Weather | Open-Meteo | free, no key |
| Database | Neon Postgres (free) | |
| Photos | stored in Postgres by default; S3-compatible (Cloudflare R2) switchable via env | zero setup now, scalable later |
| Hosting | Hugging Face Space (API), Vercel (web), EAS (store builds) | free tiers |
| Demo | `/auth/demo` creates a private 17-piece sample wardrobe, auto-deleted after 24 h | portfolio visitors can try without signing up |

## Phases

### Phase 1 — Backend ✅
- [x] Auth: register / login (Argon2id, JWT), demo accounts, account deletion (App Store rule)
- [x] Items: photo upload → EXIF stripped, WEBP → AI tags → user confirms
- [x] Outfit suggestions with weather, occasion and feedback history; output validation
- [x] Weather + city search, rate limits, translated error codes
- [x] Alembic migrations, tests (SQLite) + smoke test on Postgres, CI

### Phase 2 — App (Expo) ✅
- [x] Welcome with "Try the demo", sign in / sign up
- [x] Today: weather as the headline, occasion + note → outfits laid out as a flat-lay board with a hang-tag (title, reason, 👍/👎)
- [x] Wardrobe grid with category filter, add button
- [x] Add item: camera or gallery → AI tags → edit & save; edit / delete
- [x] Saved: liked and recent outfits
- [x] Profile: city (search or location), language, sign out, delete account, privacy link
- [x] EN/TR (Turkish locative suffixes handled), light/dark theme
- [ ] Final product name (one constant in `app/src/lib/brand.ts`)

### Phase 3 — Go live (web)
- [ ] Neon project, Hugging Face Space `smartwardrobe-api`, secrets
- [ ] Web build on Vercel → `wardrobe.fomertech.com`, CORS
- [ ] Fomer site card → Live
- [ ] Deploy sonrası /auth/demo rate limitinin kullanıcı başına çalıştığını doğrula; gerekirse TRUSTED_PROXY_HOSTS'u Space proxy adresiyle güncelle

### Phase 4 — Stores
- [ ] App icon, splash, store screenshots
- [ ] Privacy policy page (photos, account data, AI processing)
- [ ] EAS builds → TestFlight + Google Play internal testing
- [ ] Store listings (EN/TR) and review submission

### Phase AI — AI foundation
Design: [`docs/AI-00-foundation.md`](docs/AI-00-foundation.md) — Claude primary + Groq fallback, AI gateway, entitlements (Free 50 items / 5 suggestions a day, Premium 300), private R2 storage, email auth with refresh tokens, onboarding. Each phase is one PR: tests → report → review → merge.

- [x] AI-00 Foundation design — approved 19 Oct 2026
- [x] AI-01 Quick fixes — `analyze` off the event loop, Today suggestions in the query cache, trusted proxy list, `MAX_ITEMS` in config, CLAUDE.md
- [x] AI-02 Schema migration — `0002_ai_foundation` (new fields, ten tables, `item_ids` → `outfit_items`, ratings → `feedback_events`), Postgres + `alembic check` in CI
- [x] AI-03 AI gateway + entitlements — `app/ai/` (Claude primary, Groq fallback, retries, telemetry), `app/entitlements/` (plans, daily budget, grants)
- [ ] AI-04 Context + services — `app/services/` (only writer of business data), pure `ai/context.py` (§6 pre-filter, ordering, PII masking), rule-based taste summary, user outfits / edit / worn / style / vocab endpoints *(this PR)*
- [ ] AI-05a Storage — private R2 bucket with 15-min presigned links, `wardrobe_images` lifecycle, shared demo pictures, `migrate_images_to_r2.py` / `cleanup_orphans.py`, owner-only `/images`, `0004_cleanup` written (deferred to AI-09) *(this PR)*
- [ ] AI-05b Auth — 15-min access + rotating refresh tokens, email verification, password reset, app token flow
- [ ] AI-06 … AI-09 — intelligence features, onboarding, entitlements UI, V1.0 hardening; scope and order in the design doc (§13)
