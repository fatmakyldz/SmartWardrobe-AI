"""AI-09b: Sentry is off without a DSN, and what it would send carries no PII."""

from app.config import Settings
from app.observability import _before_send, init_sentry


def test_sentry_is_off_without_a_dsn():
    assert init_sentry(Settings(sentry_dsn="")) is False


def test_before_send_strips_bodies_credentials_and_identity():
    event = {
        "request": {"data": {"password": "x"}, "cookies": "sw_refresh=abc",
                    "headers": {"Authorization": "Bearer t", "Cookie": "a=b", "User-Agent": "ua"}},
        "user": {"id": "u1", "email": "fatma@example.com", "ip_address": "1.2.3.4"},
    }
    out = _before_send(event, {})
    assert out["request"] == {"headers": {"User-Agent": "ua"}}
    assert out["user"] == {"id": "u1"}
