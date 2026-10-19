import io

from PIL import Image


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
    me = client.get("/me", headers={"Authorization": f"Bearer {ok.json()['token']}"})
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
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    items = client.get("/items", headers=h).json()
    assert len(items) == 17
    assert any(i["name"] == "Beyaz tişört" for i in items)
    img = client.get(items[0]["image_url"].replace("http://testserver", ""))
    assert img.status_code == 200 and img.headers["content-type"] == "image/webp"


def test_demo_cannot_log_in_with_password(client):
    email = client.post("/auth/demo", json={}).json()["user"]["email"]
    assert client.post("/auth/login", json={"email": email, "password": "anything123"}).status_code == 401


# ── items ───────────────────────────────────────────────────────────────

def test_analyze_then_create_item(client, auth, monkeypatch):
    seen = {}

    def fake_chat(messages, model, **kw):
        seen["model"] = model
        seen["has_image"] = messages[1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        return {
            "is_clothing": True, "category": "DRESS", "subcategory": "midi dress", "name": "Bordo elbise",
            "colors": ["burgundy", "neon-unicorn", "black"], "pattern": "solid",
            "warmth": 9, "formality": 4, "seasons": ["autumn", "monsoon"],
        }

    monkeypatch.setattr("app.ai.chat_json", fake_chat)
    r = client.post("/items/analyze", files={"image": ("d.png", png_bytes(), "image/png")}, data={"lang": "tr"}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert seen == {"model": "qwen/qwen3.8-27b", "has_image": True}
    # model output is coerced into the fixed vocabularies
    assert body["tags"]["category"] == "dress"
    assert body["tags"]["colors"] == ["burgundy", "black"]
    assert body["tags"]["warmth"] == 5
    assert body["tags"]["seasons"] == ["autumn"]

    # stored image is a downscaled WEBP
    img = client.get(body["image_url"].replace("http://testserver", ""))
    stored = Image.open(io.BytesIO(img.content))
    assert stored.format == "WEBP" and max(stored.size) <= 1024

    create = client.post("/items", json={"image_key": body["image_key"], **body["tags"]}, headers=auth)
    assert create.status_code == 201
    item_id = create.json()["id"]

    upd = client.patch(f"/items/{item_id}", json={"name": "Sevdiğim elbise", "colors": ["red"]}, headers=auth)
    assert upd.json()["name"] == "Sevdiğim elbise" and upd.json()["colors"] == ["red"]

    assert client.delete(f"/items/{item_id}", headers=auth).status_code == 204
    assert client.get("/items", headers=auth).json() == []


def test_cannot_use_someone_elses_image_key(client, auth):
    other = client.post("/auth/demo", json={}).json()["token"]
    other_items = client.get("/items", headers={"Authorization": f"Bearer {other}"}).json()
    key = other_items[0]["image_url"].split("/images/")[1]
    r = client.post("/items", json={"image_key": key, "category": "top"}, headers=auth)
    assert r.status_code == 400


def test_rejects_non_image(client, auth):
    r = client.post("/items/analyze", files={"image": ("x.txt", b"hello", "text/plain")}, headers=auth)
    assert r.status_code == 415


def test_ai_not_configured(client, auth, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    r = client.post("/items/analyze", files={"image": ("d.png", png_bytes(), "image/png")}, headers=auth)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_not_configured"


def test_analyze_runs_off_the_event_loop(client, auth, monkeypatch):
    import asyncio

    import app.routers.items as items_router

    def on_loop() -> bool:
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False

    seen = {}
    real_normalize = items_router.normalize

    def spy_normalize(raw, max_mb):
        seen["normalize"] = on_loop()
        return real_normalize(raw, max_mb)

    def spy_chat(messages, model, **kw):
        seen["llm"] = on_loop()
        return {"is_clothing": True, "category": "top"}

    monkeypatch.setattr(items_router, "normalize", spy_normalize)
    monkeypatch.setattr("app.ai.chat_json", spy_chat)
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


def test_wardrobe_full_uses_max_items_setting(client, monkeypatch):
    from app.config import get_settings

    token = client.post("/auth/demo", json={}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    items = client.get("/items", headers=h).json()
    key = items[0]["image_url"].split("/images/")[1]

    monkeypatch.setattr(get_settings(), "max_items", len(items))
    r = client.post("/items", json={"image_key": key, "category": "top"}, headers=h)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "wardrobe_full"

    monkeypatch.setattr(get_settings(), "max_items", len(items) + 1)
    assert client.post("/items", json={"image_key": key, "category": "top"}, headers=h).status_code == 201


def test_max_items_default_and_env_override(monkeypatch):
    from app.config import Settings

    assert Settings().max_items == 300
    monkeypatch.setenv("MAX_ITEMS", "50")
    assert Settings().max_items == 50


# ── outfits ─────────────────────────────────────────────────────────────

def test_suggest_needs_complete_wardrobe(client, auth):
    r = client.post("/outfits/suggest", json={"occasion": "work"}, headers=auth)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "wardrobe_incomplete"


def test_suggest_validates_and_learns(client, fake_weather, monkeypatch):
    token = client.post("/auth/demo", json={"locale": "en"}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    prompts = []

    def fake_chat(messages, model, **kw):
        prompts.append(messages[1]["content"])
        # 0 white tee, 4 jeans, 12 sneakers, 11 leather jacket | 8 dress, 14 loafers
        return {
            "outfits": [
                {"title": "Rainy casual", "items": [0, 4, 12, 11, 999], "reason": "Layers for the rain."},
                {"title": "Duplicate", "items": [4, 0, 12, 11], "reason": "same set"},
                {"title": "Two tops", "items": [0, 1, 12], "reason": "invalid: no bottom"},
                {"title": "Dress up", "items": [8, 14], "reason": "Easy elegance."},
            ]
        }

    monkeypatch.setattr("app.ai.chat_json", fake_chat)
    r = client.post("/outfits/suggest", json={"occasion": "casual", "lang": "en"}, headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["weather"]["temp"] == 12.0
    titles = [o["title"] for o in data["outfits"]]
    assert titles == ["Rainy casual", "Dress up"]  # hallucinated id dropped, duplicate + incomplete removed
    assert len(data["outfits"][0]["items"]) == 4
    assert "rain" in prompts[0] and "OCCASION: casual" in prompts[0]

    first = data["outfits"][0]["id"]
    fb = client.post(f"/outfits/{first}/feedback", json={"rating": 1}, headers=h)
    assert fb.json()["rating"] == 1

    client.post("/outfits/suggest", json={"occasion": "work"}, headers=h)
    assert "USER LIKED" in prompts[1]

    liked = client.get("/outfits?liked_only=true", headers=h).json()
    assert [o["id"] for o in liked] == [first]


def test_suggest_without_weather_still_works(client, monkeypatch):
    from fastapi import HTTPException

    def boom(lat, lon):
        raise HTTPException(502, detail={"code": "weather_unavailable"})

    monkeypatch.setattr("app.routers.outfits.get_weather", boom)
    monkeypatch.setattr("app.ai.chat_json", lambda m, model, **kw: {"outfits": [{"title": "t", "items": [0, 4], "reason": "r"}]})
    token = client.post("/auth/demo", json={}).json()["token"]
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


# ── account deletion ────────────────────────────────────────────────────

def test_delete_account_removes_everything(client):
    from app.db import SessionLocal
    from app.models import Item, StoredImage, User

    token = client.post("/auth/demo", json={}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.delete("/me", headers=h).status_code == 204
    assert client.get("/me", headers=h).status_code == 401
    with SessionLocal() as db:
        assert db.query(User).count() == 0
        assert db.query(Item).count() == 0
        assert db.query(StoredImage).count() == 0


def test_rate_limit_on_suggest(client, fake_weather, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "suggest_limit", "2/hour")
    monkeypatch.setattr("app.ai.chat_json", lambda m, model, **kw: {"outfits": [{"title": "t", "items": [0, 4], "reason": "r"}]})
    token = client.post("/auth/demo", json={}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    codes = [client.post("/outfits/suggest", json={}, headers=h).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
