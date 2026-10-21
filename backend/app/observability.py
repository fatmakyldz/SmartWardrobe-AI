"""Error tracking (AI-09b). Sentry is on only when SENTRY_DSN is set; everything else is a no-op.

What leaves the server: the exception, the stack (code lines, no local variables), the route, the HTTP
method/status and the pseudonymous user id (request.state.user_id) — never request bodies, query strings
(they carry coordinates, §11), headers with credentials, e-mail addresses, IPs or photos. Expected API
errors (4xx, rate limits, 4xx AIErrors) are not reported; they are the product working. 5xx AIErrors
(a prompt file missing, every provider down) are reported from the exception handler in main.py.
"""

import logging

import sentry_sdk
from sentry_sdk.integrations.logging import ignore_logger

from .config import Settings

log = logging.getLogger("observability")

# Access log lines carry the client IP and the full path with query; the SDK would turn each into a
# breadcrumb. The "ai" logger stays: its ERROR records (provider crash, telemetry write failure) are bugs.
_IGNORED_LOGGERS = ("uvicorn.access",)
_SECRET_HEADERS = ("authorization", "cookie", "x-auth-cookie", "x-forwarded-for", "x-real-ip")


def _before_send(event: dict, hint: dict) -> dict | None:
    # Belt and braces on top of send_default_pii=False: strip anything request-shaped we don't want.
    request = event.get("request") or {}
    for key in ("data", "cookies", "query_string", "env"):
        request.pop(key, None)
    headers = request.get("headers") or {}
    for key in list(headers):
        if key.lower() in _SECRET_HEADERS:
            headers.pop(key)
    user = event.get("user") or {}
    for key in list(user):
        if key != "id":
            user.pop(key)
    return event


def _before_breadcrumb(crumb: dict, hint: dict) -> dict | None:
    # Outgoing HTTP breadcrumbs (Open-Meteo) would carry latitude/longitude in the query.
    data = crumb.get("data") or {}
    for key in ("http.query", "http.fragment"):
        data.pop(key, None)
    return crumb


def init_sentry(settings: Settings) -> bool:
    if not settings.sentry_dsn:
        return False
    for name in _IGNORED_LOGGERS:
        ignore_logger(name)
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,  # frame locals hold the ASGI scope (tokens, IP), request models, Settings
        before_send=_before_send,
        before_breadcrumb=_before_breadcrumb,
    )
    log.info("sentry on (%s)", settings.sentry_environment)
    return True


def set_sentry_user(user_id: str | None) -> None:
    """Called by the auth dependency: the pseudonymous id only, so errors group per account.
    Without a client this is a scope-dict write — cheap."""
    sentry_sdk.set_user({"id": user_id} if user_id else None)


def capture(exc: BaseException) -> None:
    """Report an exception the app handled itself (a 5xx AIError). No-op without a client."""
    sentry_sdk.capture_exception(exc)
