import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .ai import AIError
from .config import get_settings
from .ratelimit import limiter
from .routers import auth, items, me, misc, outfits

logging.basicConfig(level=logging.INFO)

settings = get_settings()

if not settings.database_url.startswith("sqlite") and settings.secret_key == "dev-only-change-me":
    raise RuntimeError("Set SECRET_KEY to a long random value before running against a real database.")
if not settings.database_url.startswith("sqlite") and not settings.cors_list:
    raise RuntimeError("Set CORS_ORIGINS (e.g. https://wardrobe.fomertech.com): credentials are allowed, so any-origin is refused.")
if not settings.database_url.startswith("sqlite") and settings.ai_debug_log:
    raise RuntimeError("AI_DEBUG_LOG prints full prompts; it is only allowed with a local SQLite database.")

app = FastAPI(
    title="SmartWardrobe API",
    version="2.0.0",
    description="Wardrobe, AI tagging and weather-aware outfit suggestions.",
)
app.state.limiter = limiter

# Real client IPs behind the hosting proxy (rate limits for anonymous endpoints).
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxy_list)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list or ["*"],  # "*" only reaches here with local SQLite (checked above)
    allow_credentials=True,  # the web app's refresh cookie
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", auth.COOKIE_HEADER],
)


@app.exception_handler(RateLimitExceeded)
def rate_limited(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": {"code": "rate_limited"}})


@app.exception_handler(AIError)
def ai_error(request: Request, exc: AIError):
    return JSONResponse(status_code=exc.status, content={"detail": {"code": exc.code, **exc.detail}})


@app.get("/", tags=["health"])
def health():
    return {"status": "ok", "service": "smartwardrobe-api"}


for r in (auth.router, me.router, items.router, outfits.router, misc.router):
    app.include_router(r)
