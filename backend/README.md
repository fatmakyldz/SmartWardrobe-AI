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
