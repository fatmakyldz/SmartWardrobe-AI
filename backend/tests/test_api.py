import io

from PIL import Image

from app.ai.providers import FAKE
from app.db import SessionLocal
from tests.helpers import answer, wardrobe


def png_bytes(color=(200, 30, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 1200), color).save(buf, "PNG")
    return buf.getvalue()


# ── auth ────────────────────────────────────────────────────────────────

def test_register_login_and_me(client):
    r = client.post("/auth/register", json={"email": "A@Example.com", "password": "supersecret1", "locale": "tr"})
    assert r.status_code == 201
    assert r.json()["user"]["email"] == "a@example.com"

    assert client.post("/auth/register", json={"email": "a@example.com", "password": "supersecret1"}).status_code == 409

    bad = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-password"})
    assert bad.status_code == 401 and bad.json()["detail"]["code"] == "invalid_credentials"

    ok = client.post("/auth/login", json={"email": "a@example.com", "password": "supersecret1"})
    assert ok.status_code == 200
    me = client.get("/me", headers={"Authorization": f"Bearer {ok.json()['access']}"})
    assert me.json()["locale"] == "tr"


def test_requires_auth(client):
    assert client.get("/items").status_code == 401
    assert client.get("/items", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_short_password_rejected(client):
    assert client.post("/auth/register", json={"email": "b@example.com", "password": "short"}).status_code == 422


def test_update_profile(client, auth):
    r = client.patch("/me", json={"city": " İstanbul ", "lat": 41.0, "lon": 29.0, "locale": "tr"}, headers=auth)
    assert r.json()["city"] == "İstanbul" and r.json()["lat"] == 41.0


# ── demo ────────────────────────────────────────────────────────────────

def test_demo_account_has_wardrobe_and_images(client):
    r = client.post("/auth/demo", json={"locale": "tr"})
    assert r.status_code == 201
    h = {"Authorization": f"Bearer {r.json()['access']}"}
    items = client.get("/items", headers=h).json()
    assert len(items) == 17
    assert any(i["name"] == "Beyaz tişört" for i in items)
    # the 17 pictures are shared system objects, not copies per demo account (§14 C5)
    assert all(i["image_key"].startswith("demo/") for i in items)
    img = client.get(items[0]["image_url"].replace("http://testserver", ""), headers=h)
    assert img.status_code == 200 and img.headers["content-type"] == "image/webp"
    assert img.headers["cache-control"] == "private, max-age=900"


def test_demo_cannot_log_in_with_password(client):
    email = client.post("/auth/demo", json={}).json()["user"]["email"]
    assert client.post("/auth/login", json={"email": email, "password": "anything123"}).status_code == 401


# ── items ───────────────────────────────────────────────────────────────

def test_analyze_then_create_item(client, auth, fake_ai):
    from app.ai.providers import ImagePart

    seen = {}

    def fake_chat(call, model):
        seen["model"] = model
        seen["has_image"] = any(isinstance(p, ImagePart) and p.data[:2] == b"\xff\xd8" for p in call.parts)
        return {
            "is_clothing": True, "category": "DRESS", "subcategory": "midi dress", "name": "Bordo elbise",
            "colors": ["burgundy", "neon-unicorn", "black"], "pattern": "solid",
            "warmth": 9, "formality": 4, "seasons": ["autumn", "monsoon"],
            "confidence": 0.62, "uncertain": ["warmth", "seasons"],
        }

    fake_ai.respond = fake_chat
    r = client.post("/items/analyze", files={"image": ("d.png", png_bytes(), "image/png")}, data={"lang": "tr"}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert seen == {"model": "fake-vision-a", "has_image": True}
    # model output is coerced into the fixed vocabularies
    assert body["tags"]["category"] == "dress"
    assert body["tags"]["colors"] == ["burgundy", "black"]
    assert body["tags"]["warmth"] == 5
    assert body["tags"]["seasons"] == ["autumn"]
    assert body["confidence"] == 0.62 and body["uncertain"] == ["warmth", "seasons"]  # the app highlights these

    # stored image is a downscaled WEBP
    img = client.get(body["image_url"].replace("http://testserver", ""), headers=auth)
    stored = Image.open(io.BytesIO(img.content))
    assert stored.format == "WEBP" and max(stored.size) <= 1024

    create = client.post("/items", json={"image_key": body["image_key"], "ai_confidence": body["confidence"], **body["tags"]},
                         headers=auth)
    assert create.status_code == 201
    item_id = create.json()["id"]
    with SessionLocal() as db:
        import uuid

        from app.models import Item

        assert db.get(Item, uuid.UUID(item_id)).ai_confidence == 0.62

    upd = client.patch(f"/items/{item_id}", json={"name": "Sevdiğim elbise", "colors": ["red"]}, headers=auth)
    assert upd.json()["name"] == "Sevdiğim elbise" and upd.json()["colors"] == ["red"]

    assert client.delete(f"/items/{item_id}", headers=auth).status_code == 204
    assert client.get("/items", headers=auth).json() == []


def test_cannot_use_someone_elses_image_key(client, auth, fake_ai):
    fake_ai.respond = lambda call, model: {"is_clothing": True, "category": "top"}
    other = client.post("/auth/register", json={"email": "other@example.com", "password": "supersecret1"}).json()
    oh = {"Authorization": f"Bearer {other['access']}"}
    key = client.post("/items/analyze", files={"image": ("d.png", png_bytes(), "image/png")}, headers=oh).json()["image_key"]
    r = client.post("/items", json={"image_key": key, "category": "top"}, headers=auth)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_image"
    # nor a shared demo picture, nor a key under one's own prefix that was never uploaded
    for bad in ("demo/white-tee.webp", f"u/{other['user']['id'].replace('-', '')}/x.webp"):
        assert client.post("/items", json={"image_key": bad, "category": "top"}, headers=auth).status_code == 400
    # an uploaded key goes on one item only
    assert client.post("/items", json={"image_key": key, "category": "top"}, headers=oh).status_code == 201
    assert client.post("/items", json={"image_key": key, "category": "top"}, headers=oh).status_code == 400


def test_rejects_non_image(client, auth):
    r = client.post("/items/analyze", files={"image": ("x.txt", b"hello", "text/plain")}, headers=auth)
    assert r.status_code == 415


def test_ai_not_configured(client, auth, monkeypatch):
    import json

    from app.ai import routing
    from app.config import get_settings

    # The real routes (Claude → Groq) with neither key set.
    real = routing.parse_config(json.loads(routing.DEFAULT_ROUTES.read_text()))
    monkeypatch.setattr(routing, "config", lambda: real)
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    r = client.post("/items/analyze", files={"image": ("d.png", png_bytes(), "image/png")}, headers=auth)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_not_configured"


def test_analyze_runs_off_the_event_loop(client, auth, monkeypatch, fake_ai):
    import asyncio

    import app.services.images as wardrobe_service

    def on_loop() -> bool:
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    seen = {}
    real_normalize = wardrobe_service.normalize

    def spy_normalize(raw, max_mb):
        seen["normalize"] = on_loop()
        return real_normalize(raw, max_mb)

    def spy_chat(call, model):
        seen["llm"] = on_loop()
        return {"is_clothing": True, "category": "top"}

    monkeypatch.setattr(wardrobe_service, "normalize", spy_normalize)
    fake_ai.respond = spy_chat
    r = client.post("/items/analyze", files={"image": ("d.png", png_bytes(), "image/png")}, headers=auth)
    assert r.status_code == 200, r.text
    # Pillow and the Groq call must run in the threadpool, not on the event loop.
    assert seen == {"normalize": False, "llm": False}


def test_rejects_too_large_image(client, auth, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    big = b"\0" * (1024 * 1024 + 10)
    r = client.post("/items/analyze", files={"image": ("big.png", big, "image/png")}, headers=auth)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "image_too_large"


def test_wardrobe_full_uses_plan_max_items(client, auth):
    from datetime import datetime, timezone

    from app.db import SessionLocal
    from app.models import EntitlementGrant, Item, User, WardrobeImage

    with SessionLocal() as db:
        user = db.query(User).one()
        uid = user.id
        db.add_all([Item(user_id=uid, image_key=f"u/{uid.hex}/{n}.webp", category="top") for n in range(50)])
        db.add(WardrobeImage(key=f"u/{uid.hex}/new.webp", user_id=uid, content_type="image/webp",
                             bytes=1, width=1, height=1))
        db.commit()
    body = {"image_key": f"u/{uid.hex}/new.webp", "category": "top"}
    r = client.post("/items", json=body, headers=auth)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "wardrobe_full"  # free plan: 50

    with SessionLocal() as db:
        db.add(EntitlementGrant(user_id=uid, limits={"max_items": 60}, source="support", reason="test",
                                created_by="test", starts_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        db.commit()
    assert client.post("/items", json=body, headers=auth).status_code == 201


def test_demo_account_is_full_and_cannot_tag(client):
    token = client.post("/auth/demo", json={}).json()["access"]
    h = {"Authorization": f"Bearer {token}"}
    key = client.get("/items", headers=h).json()[0]["image_key"]
    r = client.post("/items", json={"image_key": key, "category": "top"}, headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "wardrobe_full"  # demo plan: its 17 pieces
    r = client.post("/items/analyze", files={"image": ("d.png", png_bytes(), "image/png")}, headers=h)
    assert r.status_code == 403 and r.json()["detail"] == {"code": "feature_not_allowed", "feature": "tagging"}


# ── outfits ─────────────────────────────────────────────────────────────

def test_suggest_needs_complete_wardrobe(client, auth):
    r = client.post("/outfits/suggest", json={"occasion": "work"}, headers=auth)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "wardrobe_incomplete"


def test_suggest_validates_and_learns(client, fake_weather, fake_ai):
    token = client.post("/auth/demo", json={"locale": "en"}).json()["access"]
    h = {"Authorization": f"Bearer {token}"}
    prompts = []

    def fake_chat(call, model):
        prompts.append(call.parts[0].text)
        w = wardrobe(call)
        top, top2, bottom, shoes = w["top"][0], w["top"][1], w["bottom"][0], w["shoes"][0]
        return {
            "outfits": [
                {"title": "Smart date", "items": [top, bottom, shoes, w["outerwear"][0], 999], "reason": "Layers."},
                {"title": "Duplicate", "items": [bottom, top, shoes, w["outerwear"][0]], "reason": "same set"},
                {"title": "Two tops", "items": [top, top2, shoes], "reason": "invalid: no bottom"},
                {"title": "Dress up", "items": [w["dress"][0], shoes], "reason": "Easy elegance."},
            ]
        }

    fake_ai.respond = fake_chat
    r = client.post("/outfits/suggest", json={"occasion": "date", "lang": "en"}, headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["weather"]["temp"] == 12.0
    titles = [o["title"] for o in data["outfits"]]
    assert titles == ["Smart date", "Dress up"]  # hallucinated id dropped, duplicate + incomplete removed
    assert len(data["outfits"][0]["items"]) == 4
    assert "rain" in prompts[0] and "OCCASION: date" in prompts[0]

    first = data["outfits"][0]["id"]
    fb = client.post(f"/outfits/{first}/feedback", json={"rating": 1}, headers=h)
    assert fb.json()["rating"] == 1

    client.post("/outfits/suggest", json={"occasion": "work"}, headers=h)
    assert "RECENT FEEDBACK" in prompts[1] and "like [" in prompts[1]
    assert "TASTE SUMMARY: Likes" in prompts[1]  # first feedback event builds the summary

    liked = client.get("/outfits?liked_only=true", headers=h).json()
    assert [o["id"] for o in liked] == [first]


def _demo_with_outfit(client, monkeypatch):
    FAKE.respond = answer("bottom", "top", "shoes")
    token = client.post("/auth/demo", json={}).json()["access"]
    h = {"Authorization": f"Bearer {token}"}
    outfit = client.post("/outfits/suggest", json={}, headers=h).json()["outfits"][0]
    return h, outfit


def test_suggest_writes_outfit_items_alongside_item_ids(client, monkeypatch):
    import uuid

    from app.db import SessionLocal
    from app.models import Outfit

    h, outfit = _demo_with_outfit(client, monkeypatch)
    with SessionLocal() as db:
        o = db.get(Outfit, uuid.UUID(outfit["id"]))
        assert o.source == "ai"
        links = [(oi.position, str(oi.item_id), oi.slot) for oi in o.outfit_items]
    # same items, same order as item_ids (which the response is still built from)
    assert links == [(n, i["id"], i["category"]) for n, i in enumerate(outfit["items"])]


def test_feedback_updates_rating_and_logs_events(client, monkeypatch):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import FeedbackEvent

    h, outfit = _demo_with_outfit(client, monkeypatch)
    for rating in (1, -1, 0):
        r = client.post(f"/outfits/{outfit['id']}/feedback", json={"rating": rating}, headers=h)
        assert r.status_code == 200 and r.json()["rating"] == rating
    assert client.get("/outfits", headers=h).json()[0]["rating"] == 0
    with SessionLocal() as db:
        events = db.scalars(select(FeedbackEvent).order_by(FeedbackEvent.created_at)).all()
        assert [(e.kind, str(e.outfit_id), e.item_id) for e in events] == [
            ("like", outfit["id"], None), ("dislike", outfit["id"], None), ("unrate", outfit["id"], None)
        ]


def test_deleting_item_drops_its_outfit_items(client, monkeypatch):
    import uuid

    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import FeedbackEvent, OutfitItem

    h, outfit = _demo_with_outfit(client, monkeypatch)
    client.post(f"/outfits/{outfit['id']}/feedback", json={"rating": 1}, headers=h)
    gone = outfit["items"][1]["id"]
    assert client.delete(f"/items/{gone}", headers=h).status_code == 204

    with SessionLocal() as db:
        left = db.scalars(select(OutfitItem.item_id).where(OutfitItem.outfit_id == uuid.UUID(outfit["id"]))).all()
        assert sorted(map(str, left)) == sorted(i["id"] for i in outfit["items"] if i["id"] != gone)
        assert db.scalar(select(func.count()).select_from(OutfitItem).where(OutfitItem.item_id == uuid.UUID(gone))) == 0
        assert db.scalar(select(func.count()).select_from(FeedbackEvent)) == 1
    # the outfit is still served from item_ids, without the deleted piece (as before)
    saved = client.get("/outfits", headers=h).json()[0]
    assert [i["id"] for i in saved["items"]] == [i["id"] for i in outfit["items"] if i["id"] != gone]


def test_suggest_without_weather_still_works(client, monkeypatch):
    from fastapi import HTTPException

    def boom(lat, lon):
        raise HTTPException(502, detail={"code": "weather_unavailable"})

    monkeypatch.setattr("app.services.orchestration.get_weather", boom)
    FAKE.respond = answer()
    token = client.post("/auth/demo", json={}).json()["access"]
    r = client.post("/outfits/suggest", json={}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["weather"] is None


# ── proxy headers ───────────────────────────────────────────────────────

def _demo_codes(remote_ip: str, forwarded_for: list[str]) -> list[int]:
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app, client=(remote_ip, 50000))
    return [c.post("/auth/demo", json={}, headers={"X-Forwarded-For": ip}).status_code for ip in forwarded_for]


def test_spoofed_forwarded_for_cannot_skip_rate_limit(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_limit", "2/hour")
    # A direct (non-proxy) caller rotating X-Forwarded-For still shares one bucket.
    assert _demo_codes("203.0.113.7", ["1.1.1.1", "2.2.2.2", "3.3.3.3"]) == [201, 201, 429]


def test_trusted_proxy_forwarded_for_is_used(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_limit", "1/hour")
    # Behind the Space's load balancer (private address) each real client gets its own bucket.
    assert _demo_codes("10.16.0.4", ["198.51.100.1", "198.51.100.2", "198.51.100.1"]) == [201, 201, 429]


def test_trusted_proxy_hosts_setting(monkeypatch):
    from app.config import Settings

    assert "*" not in Settings().trusted_proxy_list
    monkeypatch.setenv("TRUSTED_PROXY_HOSTS", "")
    assert Settings().trusted_proxy_list == ["127.0.0.1", "::1"]
    monkeypatch.setenv("TRUSTED_PROXY_HOSTS", " 10.0.0.0/8 , 127.0.0.1 ")
    assert Settings().trusted_proxy_list == ["10.0.0.0/8", "127.0.0.1"]


def _client_ip(cloudflare_proxy: bool, remote_ip: str, forwarded_for: str) -> str:
    """The client IP the app sees, with the same proxy middleware and settings as main.py."""
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    from app.config import Settings

    probe = FastAPI()

    @probe.get("/ip")
    def ip(request: Request) -> str:
        return request.client.host

    probe.add_middleware(
        ProxyHeadersMiddleware, trusted_hosts=Settings(cloudflare_proxy=cloudflare_proxy).trusted_proxy_list
    )
    c = TestClient(probe, client=(remote_ip, 50000))
    return c.get("/ip", headers={"X-Forwarded-For": forwarded_for}).json()


def test_cloudflare_proxy_forwarded_for_is_used():
    # Worker → Space load balancer: X-Forwarded-For is "visitor, Cloudflare egress".
    chain = "198.51.100.1, 104.16.0.10"
    assert _client_ip(False, "10.16.0.4", chain) == "104.16.0.10"  # everyone shares the Worker's IP
    assert _client_ip(True, "10.16.0.4", chain) == "198.51.100.1"
    assert _client_ip(True, "10.16.0.4", "198.51.100.1, 2606:4700::1") == "198.51.100.1"


def test_cloudflare_proxy_still_refuses_spoofed_forwarded_for():
    # A direct caller faking the header: the load balancer appends the caller's real IP.
    assert _client_ip(True, "10.16.0.4", "1.1.1.1, 203.0.113.7") == "203.0.113.7"
    # A caller that isn't a trusted proxy at all.
    assert _client_ip(True, "203.0.113.7", "1.1.1.1") == "203.0.113.7"


def test_cloudflare_proxy_setting(monkeypatch):
    from app.config import Settings, cloudflare_ranges

    ranges = cloudflare_ranges()
    assert "173.245.48.0/20" in ranges and "2400:cb00::/32" in ranges
    assert all("/" in r and not r.startswith("#") for r in ranges)
    assert not set(ranges) & set(Settings().trusted_proxy_list)  # off by default
    monkeypatch.setenv("CLOUDFLARE_PROXY", "true")
    assert set(ranges) <= set(Settings().trusted_proxy_list)
    assert "*" not in Settings().trusted_proxy_list


# ── account deletion ────────────────────────────────────────────────────

def test_delete_account_removes_everything(client, monkeypatch):
    from app.db import SessionLocal
    from app.models import FeedbackEvent, Item, Outfit, OutfitItem, StoredImage, User, WardrobeImage

    FAKE.respond = answer()
    token = client.post("/auth/demo", json={}).json()["access"]
    h = {"Authorization": f"Bearer {token}"}
    outfit = client.post("/outfits/suggest", json={}, headers=h).json()["outfits"][0]
    client.post(f"/outfits/{outfit['id']}/feedback", json={"rating": 1}, headers=h)
    assert client.delete("/me", headers=h).status_code == 204
    assert client.get("/me", headers=h).status_code == 401
    with SessionLocal() as db:
        for model in (User, Item, Outfit, OutfitItem, FeedbackEvent):
            assert db.query(model).count() == 0, model.__tablename__
        # the shared demo pictures outlive every demo account
        assert {i.key for i in db.query(StoredImage)} == {w.key for w in db.query(WardrobeImage)}
        assert db.query(WardrobeImage).count() == 17
        assert all(w.key.startswith("demo/") and w.user_id is None for w in db.query(WardrobeImage))


def test_rate_limit_on_suggest(client, fake_weather, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "suggest_limit", "2/hour")
    FAKE.respond = answer()
    token = client.post("/auth/demo", json={}).json()["access"]
    h = {"Authorization": f"Bearer {token}"}
    codes = [client.post("/outfits/suggest", json={}, headers=h).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
