# SmartWardrobe — notes for Claude

**`docs/AI-00-foundation.md` is the approved architecture (FINAL, 19 Oct 2026).** Don't make changes that contradict it; if a task seems to need one, stop and ask. Work goes phase by phase (its §13: AI-01 → AI-09), one PR per phase, and each phase does only what its row lists — no schema, prompt or dependency changes outside the phase that owns them.

## Layout

| Path | |
|---|---|
| `backend/` | FastAPI + SQLAlchemy 2 + Alembic. `app/routers/` (auth, me, items, outfits, misc), `app/ai.py` + `app/llm.py` (Groq), `app/config.py` (all settings, env-overridable), `app/storage.py` (db / s3), `migrations/`, `tests/` |
| `app/` | Expo (React Native) app for iOS, Android, web; EN/TR. Screens in `src/app/` (Expo Router), data hooks in `src/lib/queries.ts` (TanStack Query). **Read `app/AGENTS.md` before touching the app.** |
| `docs/` | design docs (`AI-00-foundation.md`) |
| `ROADMAP.md` | phases and status |

## Commands

```bash
# backend (Python 3.13)
cd backend && pip install -r requirements-dev.txt
pytest -q                       # SQLite + TestClient; LLM calls are monkeypatched

# app (Node 22)
cd app && npm ci
npm run typecheck && npm run lint
npm run export:web              # what CI builds
```

CI (`.github/workflows/`) runs the same: `pytest -q` for `backend/**`, typecheck + lint + web export for `app/**`.

## Rules of thumb

- The LLM never writes to the DB; every structured answer is validated server-side (vocab, ids, ownership).
- Errors are `{"detail": {"code": "..."}}`; the app translates the code.
- New settings go in `backend/app/config.py` and `backend/.env.example`.
- Behaviour changes come with tests; keep existing tests green.
