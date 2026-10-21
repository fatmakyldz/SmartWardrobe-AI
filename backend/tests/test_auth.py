"""§9 auth: short access tokens, rotating refresh tokens, email verification, password reset, CORS."""

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AIRequest, AuthToken, RefreshToken, User
from app.services import email
from tests.conftest import verify_email

CREDS = {"email": "fatma@example.com", "password": "supersecret1", "name": "Fatma"}
WEB = {"X-Auth-Cookie": "1"}


def bearer(access: str) -> dict:
    return {"Authorization": f"Bearer {access}"}


def register(client, **extra) -> dict:
    r = client.post("/auth/register", json={**CREDS, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def token_from(outbox, template: str) -> str:
    msg = [m for m in outbox if m.template == template][-1]
    return parse_qs(urlparse(msg.link).query)["token"][0]


# ── access + refresh ──────────────────────────────────────────────────────

def test_login_returns_a_15_minute_access_token_and_a_refresh_token(client):
    register(client)
    r = client.post("/auth/login", json={"email": "FATMA@example.com", "password": CREDS["password"]})
    body = r.json()
    assert set(body) == {"access", "refresh", "user", "claimed"} and body["refresh"]
    claims = jwt.decode(body["access"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 15 * 60 and claims["tv"] == 0
    assert client.get("/me", headers=bearer(body["access"])).json()["email"] == "fatma@example.com"
    with SessionLocal() as db:
        rows = db.scalars(select(RefreshToken)).all()
        assert len(rows) == 2  # register + login: two sessions
        assert all(len(t.token_hash) == 64 and t.token_hash != body["refresh"] for t in rows)  # sha256 only
        assert all((t.expires_at - t.created_at).days == 30 for t in rows)


def test_refresh_rotates(client):
    first = register(client)["refresh"]
    r = client.post("/auth/refresh", json={"refresh": first})
    assert r.status_code == 200
    second = r.json()["refresh"]
    assert second != first and client.get("/me", headers=bearer(r.json()["access"])).status_code == 200
    with SessionLocal() as db:
        old = db.scalar(select(RefreshToken).where(RefreshToken.replaced_by.is_not(None)))
        new = db.get(RefreshToken, old.replaced_by)
        assert old.revoked_at is not None and new.family_id == old.family_id and new.revoked_at is None


def test_reused_refresh_token_revokes_the_family(client):
    first = register(client)["refresh"]
    second = client.post("/auth/refresh", json={"refresh": first}).json()["refresh"]
    other_device = client.post("/auth/login", json=CREDS).json()["refresh"]
    with SessionLocal() as db:  # the rotation happened a while ago: no grace
        for t in db.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_not(None))):
            t.revoked_at -= timedelta(minutes=5)
        db.commit()

    r = client.post("/auth/refresh", json={"refresh": first})  # the stolen, already spent token
    assert r.status_code == 401 and r.json()["detail"]["code"] == "refresh_reused"
    # the thief's and the user's current token are both dead; another device's session is not
    assert client.post("/auth/refresh", json={"refresh": second}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh": other_device}).status_code == 200


def test_racing_refresh_within_grace_does_not_revoke(client):
    first = register(client)["refresh"]
    second = client.post("/auth/refresh", json={"refresh": first}).json()["refresh"]
    r = client.post("/auth/refresh", json={"refresh": first})  # a second tab, a moment later
    assert r.status_code == 401 and r.json()["detail"]["code"] == "refresh_superseded"
    assert client.post("/auth/refresh", json={"refresh": second}).status_code == 200


def test_expired_unknown_and_logged_out_refresh_tokens(client):
    body = register(client)
    with SessionLocal() as db:
        db.scalar(select(RefreshToken)).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    r = client.post("/auth/refresh", json={"refresh": body["refresh"]})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "invalid_refresh"
    assert client.post("/auth/refresh", json={"refresh": "nope"}).status_code == 401
    assert client.post("/auth/refresh", json={}).status_code == 401

    live = client.post("/auth/login", json=CREDS).json()["refresh"]
    assert client.post("/auth/logout", json={"refresh": live}).status_code == 204
    assert client.post("/auth/refresh", json={"refresh": live}).json()["detail"]["code"] == "refresh_reused"


def test_token_version_bump_kills_old_access_tokens(client):
    body = register(client)
    other = client.post("/auth/login", json=CREDS).json()
    assert client.post("/auth/logout-all", headers=bearer(body["access"])).status_code == 204
    for access in (body["access"], other["access"]):
        r = client.get("/me", headers=bearer(access))
        assert r.status_code == 401 and r.json()["detail"]["code"] == "unauthorized"
    for refresh in (body["refresh"], other["refresh"]):
        assert client.post("/auth/refresh", json={"refresh": refresh}).status_code == 401
    fresh = client.post("/auth/login", json=CREDS).json()
    assert jwt.decode(fresh["access"], options={"verify_signature": False})["tv"] == 1
    assert client.get("/me", headers=bearer(fresh["access"])).status_code == 200


def test_access_tokens_without_version_or_expired_are_refused(client):
    from app.config import get_settings

    user_id = register(client)["user"]["id"]
    key = get_settings().secret_key
    now = datetime.now(timezone.utc)
    legacy = jwt.encode({"sub": user_id, "iat": now, "exp": now + timedelta(days=30)}, key, algorithm="HS256")
    expired = jwt.encode({"sub": user_id, "iat": now - timedelta(minutes=20), "exp": now - timedelta(minutes=5),
                          "tv": 0}, key, algorithm="HS256")
    for token in (legacy, expired):
        assert client.get("/me", headers=bearer(token)).status_code == 401


# ── the web: refresh token as an httpOnly cookie ──────────────────────────

def test_web_refresh_cookie():
    web = TestClient(app, base_url="https://testserver")
    r = web.post("/auth/register", json=CREDS, headers=WEB)
    assert r.status_code == 201 and r.json()["refresh"] is None  # never readable by page scripts
    cookie = r.headers["set-cookie"]
    for part in ("sw_refresh=", "HttpOnly", "Secure", "SameSite=lax", "Path=/auth", "Max-Age=2592000"):
        assert part in cookie
    first = web.cookies.get("sw_refresh")

    r = web.post("/auth/refresh", headers=WEB)  # no body: the cookie carries it
    assert r.status_code == 200 and r.json()["refresh"] is None and web.cookies.get("sw_refresh") != first

    assert web.post("/auth/logout", headers=WEB).status_code == 204
    assert web.cookies.get("sw_refresh") is None
    assert web.post("/auth/refresh", headers=WEB).status_code == 401


def test_cors_allows_the_web_app_with_credentials_and_refuses_others(client):
    pre = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,x-auth-cookie"}
    ok = client.options("/auth/refresh", headers={"Origin": "https://wardrobe.fomertech.com", **pre})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "https://wardrobe.fomertech.com"
    assert ok.headers["access-control-allow-credentials"] == "true"

    bad = client.options("/auth/refresh", headers={"Origin": "https://evil.example", **pre})
    assert bad.status_code == 400 and "access-control-allow-origin" not in bad.headers
    simple = client.get("/", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in simple.headers


@pytest.mark.parametrize("origins", ["", "*", "https://wardrobe.fomertech.com,*"])
def test_cors_origins_are_required_outside_local_sqlite(monkeypatch, origins):
    # With credentials allowed, "*" makes Starlette echo any Origin back, so it is refused like empty.
    import importlib

    import app.main as main
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "database_url", "postgresql://u:p@db/x")
    monkeypatch.setattr(s, "cors_origins", origins)
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        importlib.reload(main)
    monkeypatch.undo()
    importlib.reload(main)


# ── email verification (§14 C3) ───────────────────────────────────────────

def test_register_sends_verification_and_verify_marks_the_email(client, outbox):
    body = register(client, locale="tr")
    assert body["user"]["email_verified_at"] is None
    msg = outbox[-1]
    assert msg.to == "fatma@example.com" and msg.template == "verify_email" and "doğrula" in msg.subject
    assert msg.link.startswith("https://wardrobe.fomertech.com/auth/verify?token=")
    assert "smartwardrobe://auth/verify?token=" in msg.text

    token = token_from(outbox, "verify_email")
    r = client.post("/auth/verify", json={"token": token})
    assert r.status_code == 200 and r.json()["email_verified_at"] is not None
    again = client.post("/auth/verify", json={"token": token})  # single use
    assert again.status_code == 400 and again.json()["detail"]["code"] == "invalid_token"


def test_verification_token_expires_after_24h(client, outbox):
    register(client)
    with SessionLocal() as db:
        t = db.scalar(select(AuthToken))
        assert round((t.expires_at - datetime.now(timezone.utc).replace(tzinfo=t.expires_at.tzinfo)).total_seconds() / 3600) == 24
        t.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.post("/auth/verify", json={"token": token_from(outbox, "verify_email")}).status_code == 400


def test_resend_verification_replaces_the_link_and_is_limited(client, outbox):
    h = bearer(register(client)["access"])
    old = token_from(outbox, "verify_email")
    assert client.post("/auth/resend-verification", headers=h).status_code == 204
    new = token_from(outbox, "verify_email")
    assert new != old
    assert client.post("/auth/verify", json={"token": old}).status_code == 400  # superseded
    for _ in range(4):
        client.post("/auth/resend-verification", headers=h)
    assert client.post("/auth/resend-verification", headers=h).status_code == 429  # 5/hour
    assert client.post("/auth/verify", json={"token": token_from(outbox, "verify_email")}).status_code == 200


def test_unverified_accounts_get_the_small_plan_until_verified(client, unverified_auth, fake_ai):
    """C3 (a′): before the email is confirmed an account tags its first pieces and sees a first outfit on
    the `unverified` plan (5 pieces, 3 requests/day); confirming the email moves it to free."""
    from app.db import SessionLocal
    from app.entitlements import entitlements
    from app.models import User
    from tests.helpers import answer
    from tests.test_api import png_bytes

    with SessionLocal() as db:
        ent = entitlements(db.query(User).one(), db)
    assert (ent.plan, ent.max_items, ent.daily_ai_requests) == ("unverified", 5, 3)
    assert ent.allowed_features == {"tagging", "suggest", "intent"}

    fake_ai.respond = lambda call, model: {"is_clothing": True, "category": "dress"} if call.schema_name == "tagging" \
        else answer("dress")(call, model)
    r = client.post("/items/analyze", files={"image": ("d.png", png_bytes(), "image/png")}, headers=unverified_auth)
    assert r.status_code == 200 and r.json()["ai_skipped"] is None and r.json()["tags"]["category"] == "dress"
    assert client.post("/items", json={"image_key": r.json()["image_key"], "category": "dress"},
                       headers=unverified_auth).status_code == 201
    assert client.post("/outfits/suggest", json={}, headers=unverified_auth).status_code == 200  # the first outfit
    assert client.post("/outfits/capsule", json={}, headers=unverified_auth).json()["detail"]["code"] == "feature_not_allowed"

    # 3 counted requests a day, then budget_exceeded; 5 pieces, then wardrobe_full
    client.post("/outfits/suggest", json={}, headers=unverified_auth)
    client.post("/outfits/suggest", json={}, headers=unverified_auth)
    r = client.post("/outfits/suggest", json={}, headers=unverified_auth)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "budget_exceeded"
    with SessionLocal() as db:
        from app.models import Item
        uid = db.query(User).one().id
        db.add_all([Item(user_id=uid, image_key=f"u/{uid.hex}/{n}.webp", category="top") for n in range(4)])
        db.commit()
    r = client.post("/items", json={"image_key": f"u/{uid.hex}/x.webp", "category": "top"}, headers=unverified_auth)
    assert r.json()["detail"]["code"] == "wardrobe_full"

    verify_email("fatma@example.com")
    with SessionLocal() as db:
        ent = entitlements(db.query(User).one(), db)
    assert (ent.plan, ent.max_items, ent.daily_ai_requests) == ("free", 50, 5)
    assert client.post("/outfits/suggest", json={}, headers=unverified_auth).status_code == 200  # free's 5, 3 spent


def test_demo_accounts_need_no_verification(client):
    from app.ai.providers import FAKE
    from tests.helpers import answer

    FAKE.respond = answer()
    h = bearer(client.post("/auth/demo", json={}).json()["access"])
    assert client.post("/outfits/suggest", json={}, headers=h).status_code == 200


# ── password reset ────────────────────────────────────────────────────────

def test_forgot_does_not_reveal_accounts(client, outbox):
    register(client)
    outbox.clear()
    known = client.post("/auth/forgot", json={"email": "fatma@example.com"})
    unknown = client.post("/auth/forgot", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()
    assert [m.to for m in outbox] == ["fatma@example.com"]
    assert outbox[0].link.startswith("https://wardrobe.fomertech.com/auth/reset?token=")


def test_reset_changes_password_and_kills_every_session(client, outbox):
    body = register(client)
    other = client.post("/auth/login", json=CREDS).json()
    client.post("/auth/forgot", json={"email": "fatma@example.com"})
    token = token_from(outbox, "reset_password")

    short = client.post("/auth/reset", json={"token": token, "password": "short"})
    assert short.status_code == 422
    assert client.post("/auth/reset", json={"token": token, "password": "brand-new-pass"}).status_code == 204

    for session in (body, other):
        assert client.post("/auth/refresh", json={"refresh": session["refresh"]}).status_code == 401
        assert client.get("/me", headers=bearer(session["access"])).status_code == 401
    assert client.post("/auth/login", json=CREDS).status_code == 401
    fresh = client.post("/auth/login", json={"email": CREDS["email"], "password": "brand-new-pass"}).json()
    assert fresh["user"]["email_verified_at"] is not None  # the link proved the address
    assert client.post("/auth/reset", json={"token": token, "password": "another-pass1"}).status_code == 400


def test_reset_token_lasts_one_hour(client, outbox):
    register(client)
    client.post("/auth/forgot", json={"email": "fatma@example.com"})
    with SessionLocal() as db:
        t = db.scalar(select(AuthToken).where(AuthToken.purpose == "reset_password"))
        assert round((t.expires_at - datetime.now(timezone.utc).replace(tzinfo=t.expires_at.tzinfo)).total_seconds() / 60) == 60
        t.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    r = client.post("/auth/reset", json={"token": token_from(outbox, "reset_password"), "password": "brand-new-pass"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_token"


def test_forgot_is_rate_limited(client):
    codes = [client.post("/auth/forgot", json={"email": f"x{n}@example.com"}).status_code for n in range(6)]
    assert codes == [200] * 5 + [429]


# ── account deletion ──────────────────────────────────────────────────────

def test_account_deletion_removes_sessions_and_anonymises_telemetry(client):
    body = register(client)
    uid = uuid.UUID(body["user"]["id"])
    client.post("/auth/forgot", json={"email": "fatma@example.com"})
    with SessionLocal() as db:
        db.add(AIRequest(subject_id=uid, feature="suggest", prompt_version="v1", status="ok"))
        db.add(AIRequest(subject_id=uuid.uuid4(), feature="suggest", prompt_version="v1", status="ok"))
        db.commit()
    assert client.delete("/me", headers=bearer(body["access"])).status_code == 204
    with SessionLocal() as db:
        assert db.query(RefreshToken).count() == 0 and db.query(AuthToken).count() == 0
        assert db.query(User).count() == 0
        subjects = set(db.scalars(select(AIRequest.subject_id)))
        assert uid not in subjects and None in subjects and len(subjects) == 2


# ── email service ─────────────────────────────────────────────────────────

def test_resend_backend_payload(monkeypatch):
    from app.config import get_settings

    sent = {}

    class Ok:
        status_code = 200
        text = ""

    def fake_post(url, **kw):
        sent.update(url=url, **kw)
        return Ok()

    monkeypatch.setattr(get_settings(), "resend_api_key", "re_test")
    monkeypatch.setattr(email.httpx, "post", fake_post)
    link, app_link = email.links("reset", "abc")
    assert email.send("reset_password", "a@example.com", {"link": link, "app_link": app_link}, "en")
    assert sent["url"] == "https://api.resend.com/emails"
    assert sent["headers"]["Authorization"] == "Bearer re_test"
    payload = sent["json"]
    assert payload["from"] == "SmartWardrobe <noreply@fomertech.com>" and payload["to"] == ["a@example.com"]
    assert "https://wardrobe.fomertech.com/auth/reset?token=abc" in payload["text"] and "href=" in payload["html"]
    assert email.OUTBOX == []
