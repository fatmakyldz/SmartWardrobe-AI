"""AI-09a: data export, ai_requests retention."""

from datetime import datetime, timedelta, timezone

from app.ai.telemetry import anonymize_old_requests
from app.db import SessionLocal
from app.models import AIRequest, Item, User
from tests.helpers import answer


def test_export_returns_the_accounts_data_as_json(client, auth, fake_ai):
    with SessionLocal() as db:
        u = db.query(User).one()
        db.add_all([Item(user_id=u.id, image_key=f"u/{u.id.hex}/{c}.webp", category=c, colors=["black"]) for c in ("top", "bottom")])
        db.commit()
    fake_ai.respond = answer()
    r = client.post("/outfits/suggest", json={}, headers=auth)
    assert r.status_code == 200
    outfit_id = r.json()["outfits"][0]["id"]
    assert client.post(f"/outfits/{outfit_id}/feedback", json={"rating": 1}, headers=auth).status_code == 200

    r = client.get("/me/export", headers=auth)
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"].startswith("attachment;")
    body = r.json()
    assert body["format"] == "smartwardrobe-export/1"
    assert body["account"]["email"] == "fatma@example.com" and "password" not in str(body["account"])
    assert {i["category"] for i in body["items"]} == {"top", "bottom"}
    assert all(i["photo_url"] for i in body["items"])
    assert len(body["outfits"]) >= 1 and set(body["outfits"][0]["item_ids"]) <= {i["id"] for i in body["items"]}
    assert body["feedback"] and body["feedback"][-1]["kind"] == "like"
    # Usage records still linked to the account are personal data too; prompts never are.
    assert body["usage"]["daily_counters"] and body["usage"]["daily_counters"][0]["feature"] == "suggest"
    assert body["usage"]["ai_requests"][0]["feature"] == "suggest" and "prompt" not in str(body["usage"]).lower()
    assert body["sessions"] and set(body["sessions"][0]) == {"device", "signed_in_at", "last_used_at", "expires_at"}


def test_export_is_limited_to_five_an_hour_and_sees_only_your_data(client, auth, fake_ai):
    other = client.post("/auth/register", json={"email": "other@example.com", "password": "supersecret1", "name": "O", "locale": "en"})
    assert other.status_code == 201
    with SessionLocal() as db:
        u = db.query(User).filter_by(email="other@example.com").one()
        db.add(Item(user_id=u.id, image_key=f"u/{u.id.hex}/x.webp", category="dress"))
        db.commit()
    for _ in range(5):
        body = client.get("/me/export", headers=auth).json()
        assert body["account"]["email"] == "fatma@example.com" and body["items"] == []
    r = client.get("/me/export", headers=auth)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"


def test_export_requires_auth(client):
    assert client.get("/me/export").status_code == 401


def test_old_ai_requests_lose_their_subject_after_90_days():
    now = datetime(2026, 10, 21, tzinfo=timezone.utc)
    with SessionLocal() as db:
        u = User(email="r@example.com", password_hash="x")
        db.add(u)
        db.flush()
        for age in (1, 89, 91, 400):
            db.add(AIRequest(subject_id=u.id, feature="suggest", prompt_version="v1", status="ok",
                             created_at=now - timedelta(days=age)))
        db.commit()
        assert anonymize_old_requests(db, now=now, dry_run=True) == 2
        assert db.query(AIRequest).filter(AIRequest.subject_id.is_(None)).count() == 0  # dry run
        assert anonymize_old_requests(db, now=now) == 2
        db.commit()
        kept = db.query(AIRequest).filter(AIRequest.subject_id == u.id).count()
        assert kept == 2 and db.query(AIRequest).count() == 4  # rows stay, only the subject goes
