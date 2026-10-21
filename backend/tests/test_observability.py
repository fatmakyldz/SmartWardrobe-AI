"""AI-09b: Sentry is off without a DSN; with one, only unexpected errors are reported and nothing
private (tokens, cookies, coordinates, e-mail, IP, request bodies, settings) is in the event."""

import json

import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from app.ai.errors import AIError
from app.config import Settings
from app.observability import _before_send, init_sentry
from tests.conftest import verify_email


def test_sentry_is_off_without_a_dsn():
    assert init_sentry(Settings(sentry_dsn="")) is False


def test_before_send_strips_bodies_credentials_query_and_identity():
    event = {
        "request": {"data": {"password": "x"}, "cookies": "sw_refresh=abc", "query_string": "lat=41&lon=28", "env": {"REMOTE_ADDR": "1.2.3.4"},
                    "headers": {"Authorization": "Bearer t", "Cookie": "a=b", "X-Forwarded-For": "1.2.3.4", "User-Agent": "ua"}},
        "user": {"id": "u1", "email": "fatma@example.com", "ip_address": "1.2.3.4"},
    }
    out = _before_send(event, {})
    assert out["request"] == {"headers": {"User-Agent": "ua"}}
    assert out["user"] == {"id": "u1"}


class _Capture(Transport):
    def __init__(self):
        super().__init__()
        self.events: list[dict] = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type == "event":
                self.events.append(item.payload.json)


@pytest.fixture
def sentry(monkeypatch):
    transport = _Capture()
    real_init = sentry_sdk.init
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: real_init(transport=transport, **kw))
    assert init_sentry(Settings(sentry_dsn="https://k@o.ingest.sentry.io/1")) is True
    yield transport
    sentry_sdk.flush()
    sentry_sdk.get_global_scope().set_client(None)  # later tests run with Sentry off again


def test_only_unexpected_errors_are_reported_and_they_carry_nothing_private(client, sentry, monkeypatch):
    from app.main import app

    cl = TestClient(app, raise_server_exceptions=False)
    r = cl.post("/auth/register", json={"email": "fatma@example.com", "password": "supersecret1", "name": "Fatma", "locale": "en"})
    token = r.json()["access"]
    h = {"Authorization": f"Bearer {token}"}
    verify_email("fatma@example.com")

    # Expected errors: nothing reported.
    assert cl.get("/me").status_code == 401
    assert cl.post("/auth/login", json={"email": "x"}).status_code == 422
    assert cl.get("/outfits/00000000-0000-0000-0000-000000000000", headers=h).status_code in (404, 405)
    assert cl.patch("/items/00000000-0000-0000-0000-000000000000", json={"name": "x"}, headers=h).status_code == 404
    sentry_sdk.flush()
    assert sentry.events == []

    # A crash: one event, with the route and the pseudonymous id, and nothing else about the person.
    def boom(lat, lon):
        secret = token  # noqa: F841 — a local that must not travel
        raise RuntimeError("weather down")

    monkeypatch.setattr("app.routers.misc.get_weather", boom)
    # (values built at runtime: the event carries source lines of this file, which must not match)
    cookie, query = "".join(["sw", "_", "refresh"]), "&".join([f"lat={41.01}", f"lon={28.97}"])
    assert cl.get(f"/weather?{query}", headers=h, cookies={cookie: "abc" + "def"}).status_code == 500
    sentry_sdk.flush()
    assert len(sentry.events) == 1
    ev = sentry.events[0]
    assert ev["user"] == {"id": ev["user"]["id"]} and ev["user"]["id"]
    blob = json.dumps(ev)
    for private in (token[:24], cookie, "abc" + "def", query[:9], query[-9:], "@".join(["fatma", "example.com"]), "super" + "secret1"):
        assert private not in blob, private
    assert "weather down" in blob

    # A 5xx AIError goes through the app's own handler and is still reported; a 4xx one is not.
    @app.get("/_boom_ai")
    def _boom_ai(code: str):
        raise AIError(code)

    assert cl.get("/_boom_ai?code=prompt_not_found").status_code == 500
    assert cl.get("/_boom_ai?code=budget_exceeded").status_code == 429
    sentry_sdk.flush()
    assert len(sentry.events) == 2 and "prompt_not_found" in json.dumps(sentry.events[1])
