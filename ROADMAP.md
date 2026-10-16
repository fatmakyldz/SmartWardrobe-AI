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

### Phase 4 — Stores
- [ ] App icon, splash, store screenshots
- [ ] Privacy policy page (photos, account data, AI processing)
- [ ] EAS builds → TestFlight + Google Play internal testing
- [ ] Store listings (EN/TR) and review submission
