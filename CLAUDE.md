# SmartWardrobe — notes for Claude

**`docs/AI-00-foundation.md` is the approved architecture (FINAL, 19 Oct 2026).** Don't make changes that contradict it; if a task seems to need one, stop and ask. Work goes phase by phase (its §13: AI-01 → AI-09), one PR per phase, and each phase does only what its row lists — no schema, prompt or dependency changes outside the phase that owns them.

## Layout

| Path | |
|---|---|
| `backend/` | FastAPI + SQLAlchemy 2 + Alembic. `app/routers/` (auth, me, items, outfits, misc), `app/ai/` (gateway, routing, providers anthropic/groq/fake, prompts, schemas, features; `context.py` and `analysis.py` are pure — DTOs in, DTOs out; models only in `routes.default.json`), `app/entitlements/` (plans, daily budget), `app/services/` (the only writers of business data; `orchestration.py` hands DTOs to the pure `ai/context.py`), `app/config.py` (all settings, env-overridable), `app/storage.py` (db / s3), `migrations/`, `scripts/`, `tests/` |
| `app/` | Expo (React Native) app for iOS, Android, web; EN/TR. Screens in `src/app/` (Expo Router), data hooks in `src/lib/queries.ts` (TanStack Query). **Read `app/AGENTS.md` before touching the app.** |
| `docs/` | design docs (`AI-00-foundation.md`) |
| `ROADMAP.md` | phases and status |

## Commands

```bash
# backend (Python 3.13)
cd backend && pip install -r requirements-dev.txt
pytest -q                       # SQLite + TestClient; every AI route points at the fake provider
TEST_DATABASE_URL=postgresql://… pytest -q   # same suite on Postgres (CI does both)
alembic upgrade head && alembic check        # migrations match the models

# app (Node 22)
cd app && npm ci
npm run typecheck && npm run lint
npm run export:web              # what CI builds
```

CI (`.github/workflows/`) runs the same: `pytest -q` on SQLite and Postgres plus migrations up/down/up with `alembic check` for `backend/**`; typecheck + lint + web export for `app/**`.

## Rules of thumb

- The LLM never writes to the DB; every structured answer is validated server-side (vocab, ids, ownership).
- Routers don't write to the DB: they call `app/services/`. Services never import `app.ai` (except `orchestration.py`, which only builds DTOs); `ai/context.py` stays pure (DTOs in, DTO out, `today` passed in).
- Errors are `{"detail": {"code": "..."}}`; the app translates the code.
- New settings go in `backend/app/config.py` and `backend/.env.example`.
- Behaviour changes come with tests; keep existing tests green.
