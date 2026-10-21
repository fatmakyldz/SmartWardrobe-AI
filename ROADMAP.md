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
- [x] Neon project, Hugging Face Space `smartwardrobe-api`, secrets
- [x] Web build on Vercel → `wardrobe.fomertech.com`, CORS (at the edge, `api.fomertech.com` Worker)
- [ ] Fomer site card → Live
- [ ] Deploy sonrası /auth/demo rate limitinin kullanıcı başına çalıştığını doğrula; gerekirse TRUSTED_PROXY_HOSTS'u Space proxy adresiyle güncelle

### Phase 4 — Stores
- [ ] App icon, splash, store screenshots
- [x] Privacy policy page (photos, account data, AI processing) — in the app at `/privacy` (EN/TR); `wardrobe.fomertech.com/privacy` is the public URL for the stores
- [ ] EAS builds → TestFlight + Google Play internal testing
- [ ] Store listings (EN/TR) and review submission — privacy-form answers (App Privacy / Data safety), permissions and review notes in `docs/store/privacy-forms.md`; listing texts wait for the name

### Phase AI — AI foundation
Design: [`docs/AI-00-foundation.md`](docs/AI-00-foundation.md) — Claude primary + Groq fallback, AI gateway, entitlements (Free 50 items / 5 suggestions a day, Premium 300), private R2 storage, email auth with refresh tokens, onboarding. Each phase is one PR: tests → report → review → merge.

- [x] AI-00 Foundation design — approved 19 Oct 2026
- [x] AI-01 Quick fixes — `analyze` off the event loop, Today suggestions in the query cache, trusted proxy list, `MAX_ITEMS` in config, CLAUDE.md
- [x] AI-02 Schema migration — `0002_ai_foundation` (new fields, ten tables, `item_ids` → `outfit_items`, ratings → `feedback_events`), Postgres + `alembic check` in CI
- [x] AI-03 AI gateway + entitlements — `app/ai/` (Claude primary, Groq fallback, retries, telemetry), `app/entitlements/` (plans, daily budget, grants)
- [x] AI-04 Context + services — `app/services/` (only writer of business data), pure `ai/context.py` (§6 pre-filter, ordering, PII masking), rule-based taste summary, user outfits / edit / worn / style / vocab endpoints
- [x] AI-05a Storage — private R2 bucket with 15-min presigned links, `wardrobe_images` lifecycle, shared demo pictures, `migrate_images_to_r2.py` / `cleanup_orphans.py`, owner-only `/images`, `0004_cleanup` written (deferred to AI-09)
- [x] AI-05b Auth — 15-min access + rotating refresh tokens (web: httpOnly cookie), email verification (Resend), password reset, app token flow, API at api.fomertech.com
- [x] AI-06 Intelligence features — `POST /outfits/intent` and `SuggestIn.request` (free text → vocabulary values via `intent/v1`, hard avoid-filter in the context), `GET /items/analysis` (deterministic gaps: `ai/analysis.py`, no AI request, every plan), `POST /outfits/capsule` (deterministic capsule + `capsule_explain/v1`, premium feature; premium tier → mid model)
- [x] AI-07a Onboarding + personalization — three style questions before any account (`onboarding`), answers sent with `POST /auth/demo`, the demo's first suggestion without a tap, "Set up your own wardrobe" (`claim`: register with `claim_demo_token`, optionally keeping the 17 pieces, outfits and likes), `style` screen for explicit preferences (`/me/style`)
- [x] AI-07b Screens for the intelligence features — Today's text field can be sent as a parsed `request` ("Let the AI read it") with the understood intent shown back; "Wore it today" and Edit on every outfit board; `outfit/[id]` editor (edit a suggestion → `ai_edited`, or build one from the wardrobe); `analysis` (what's missing, every plan) and `capsule` (premium) screens from the Wardrobe tab; `OutfitOut` gains `source` and `worn_at`
- [x] AI-07c First pieces — onboarding's second path "Start with 3 of my own pieces": sign-up, three photos in a row with "+N outfits unlocked" after each save (deterministic analysis), straight to Today for an automatic first outfit; the first outfit comes without a tap for every account, not only the demo. Design doc **C3 (a′)**: unverified accounts run on the small `unverified` plan (5 pieces, 3 requests/day, tagging + suggest + intent) instead of no AI, so the first outfit doesn't wait for the email link; verifying moves them to `free`. `scripts/ai_report.py` reports time-to-first-outfit and unverified → verified conversion
- [x] AI-07d Progressive wardrobe — Today shows one "next piece to add" card from the deterministic analysis (everyday occasions first, then the piece-specific `few_partners` / `orphan_items` nudges), its button opens the camera with the category as the hint; tagging prompt v2 returns `confidence` + `uncertain` fields, the tag editor marks those "worth a check", `ai_confidence` stored on the item
- [x] AI-07e Taste summary depth — the rule-based summary (no LLM) now also reads patterns ("Likes knit pieces", "Skips floral"), the go-to top + bottom pairing, layering, and weights worn outfits double; still one line in the suggest context, prompt untouched
- [x] i18n infrastructure — one language list each side (`vocab.LANGS` / `SUPPORTED_LANGS`), device-language detection and the Profile picker read it, unknown codes fall back to English; no new language yet (chosen from store data after launch)
- [ ] AI-08 Entitlements UI + usage — `GET /me/entitlements` (plan, limits, features, today's usage, what verifying unlocks); Today shows suggestions left, Profile shows the plan card, limit and verify messages take their numbers from the API; feature gating (`user_outfits`, `capsule`) replaces `is_demo` checks; `reconcile_usage.py` rebuilds `usage_counters` from `ai_requests` *(this PR)*
- [ ] AI-09a Hardening — `GET /me/export` (data portability) + “Download my data” in Profile, privacy policy page (`/privacy`, linked from Profile and sign-up), `ai_requests.subject_id` anonymised after 90 days (`cleanup_orphans.py`, now scheduled weekly by `cleanup.yml`), uptime note *(this PR)*
- [x] AI-09b Error tracking — Sentry on both sides, off until a DSN is set: backend `sentry-sdk[fastapi]` (`observability.py`, 5xx only, PII stripped), app `@sentry/react-native` (`lib/observability.ts`, `expoRouterIntegration`, `Sentry.wrap`, ErrorBoundary capture, Metro config for debug ids, Expo plugin for source-map upload)
- [ ] AI-09c Cleanup migration — **R2 migration verified and `STORAGE_BACKEND=s3` live since 22 Oct 2026** (73 images, `--verify` OK) → `0004_cleanup` not before **29 Oct 2026**, after a Neon branch/backup (§14 C9); the other §2 retention rows (`usage_counters` after 400 days, expired `refresh_tokens` after 30 days) and the `ai_requests` 13-month roll-up (due from Nov 2027)
- [ ] Store metadata, brand/bundle id, builds — see Phase 4
