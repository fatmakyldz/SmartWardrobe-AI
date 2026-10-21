"""Error tracking (AI-09b). Sentry is on only when SENTRY_DSN is set; everything else is a no-op.

What leaves the server: the exception, the stack, the route, the HTTP method/status and the pseudonymous
user id (request.state.user_id) — never request bodies, headers with credentials, e-mail addresses or
photos. Expected API errors (4xx, AIError, rate limits) are not reported; they are the product working.
"""

import logging

from .config import Settings

log = logging.getLogger("observability")

_IGNORED_LOGGERS = ("ai",)  # the AI telemetry log line is a record, not an error


def _before_send(event: dict, hint: dict) -> dict | None:
    # Belt and braces on top of send_default_pii=False: strip anything request-shaped we don't want.
    request = event.get("request") or {}
    for key in ("data", "cookies"):
        request.pop(key, None)
    headers = request.get("headers") or {}
    for key in list(headers):
        if key.lower() in ("authorization", "cookie", "x-auth-cookie"):
            headers.pop(key)
    user = event.get("user") or {}
    for key in ("email", "ip_address", "username"):
        user.pop(key, None)
    return event


def init_sentry(settings: Settings) -> bool:
    if not settings.sentry_dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import ignore_logger
    from sentry_sdk.integrations.starlette import StarletteIntegration

    for name in _IGNORED_LOGGERS:
        ignore_logger(name)
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
        before_send=_before_send,
        integrations=[
            StarletteIntegration(transaction_style="endpoint", failed_request_status_codes={*range(500, 600)}),
            FastApiIntegration(transaction_style="endpoint", failed_request_status_codes={*range(500, 600)}),
        ],
    )
    log.info("sentry on (%s)", settings.sentry_environment)
    return True


def set_sentry_user(user_id: str | None) -> None:
    """Called by the auth dependency: the pseudonymous id only, so errors group per account."""
    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover
        return
    sentry_sdk.set_user({"id": user_id} if user_id else None)
