"""AI-07a: onboarding answers at demo creation, and claiming a demo account on registration (§10)."""

from app.db import SessionLocal
from app.models import FeedbackEvent, Item, Outfit, User, WardrobeImage
from tests.helpers import answer

STYLE = {"answers": {"q1": "minimal", "q2": ["neutral", "dark"], "q3": "comfort"}, "liked_colors": ["navy"]}


def _demo(client, fake_ai, style=STYLE):
    r = client.post("/auth/demo", json={"locale": "tr", "style_profile": style})
    assert r.status_code == 201, r.text
    token = r.json()["access"]
    h = {"Authorization": f"Bearer {token}"}
    fake_ai.respond = answer("top", "bottom", "shoes")
    outfit = client.post("/outfits/suggest", json={"occasion": "casual"}, headers=h).json()["outfits"][0]
    assert client.post(f"/outfits/{outfit['id']}/feedback", json={"rating": 1}, headers=h).status_code == 200
    return token, h, outfit


def _counts(email):
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == email).one()
        return {
            "profile": u.style_profile, "summary": u.style_summary,
            "items": db.query(Item).filter(Item.user_id == u.id).count(),
            "outfits": db.query(Outfit).filter(Outfit.user_id == u.id).count(),
            "events": db.query(FeedbackEvent).filter(FeedbackEvent.user_id == u.id).count(),
            "own_images": db.query(WardrobeImage).filter(WardrobeImage.user_id == u.id).count(),
            "demo_users": db.query(User).filter(User.is_demo).count(),
        }


def test_demo_takes_onboarding_answers_and_they_reach_the_prompt(client, fake_ai):
    _, h, _ = _demo(client, fake_ai)
    style = client.get("/me/style", headers=h).json()
    assert style["answers"] == STYLE["answers"] and style["liked_colors"] == ["navy"]
    _, call = fake_ai.calls[-1]
    assert "STYLE: prefers style minimal; palette neutral, dark; likes colours navy; priority comfort" in call.parts[0].text
    # Bad vocabulary is a 422, not a silently stored value.
    assert client.post("/auth/demo", json={"style_profile": {"answers": {"q1": "goth"}}}).status_code == 422


def test_claim_moves_profile_only_by_default(client, fake_ai, outbox):
    token, _, _ = _demo(client, fake_ai)
    r = client.post("/auth/register", json={"email": "f@example.com", "password": "supersecret1",
                                            "claim_demo_token": token})
    assert r.status_code == 201, r.text
    assert r.json()["claimed"] == {"style_profile": True, "items": 0, "outfits": 0, "feedback_events": 0}
    c = _counts("f@example.com")
    assert c["profile"]["answers"]["q1"] == "minimal" and c["summary"]  # the taste summary came along
    assert (c["items"], c["outfits"], c["events"], c["demo_users"]) == (0, 0, 0, 0)  # demo account gone
    h = {"Authorization": f"Bearer {r.json()['access']}"}
    assert client.get("/me/style", headers=h).json()["liked_colors"] == ["navy"]


def test_claim_with_items_copies_pieces_and_remaps_outfits(client, fake_ai, outbox):
    token, _, outfit = _demo(client, fake_ai)
    r = client.post("/auth/register", json={"email": "f@example.com", "password": "supersecret1",
                                            "claim_demo_token": token, "keep_demo_items": True})
    assert r.status_code == 201, r.text
    assert r.json()["claimed"] == {"style_profile": True, "items": 17, "outfits": 1, "feedback_events": 1}
    c = _counts("f@example.com")
    assert (c["items"], c["outfits"], c["events"], c["own_images"], c["demo_users"]) == (17, 1, 1, 17, 0)
    h = {"Authorization": f"Bearer {r.json()['access']}"}
    items = client.get("/items", headers=h).json()
    assert all(not i["image_key"].startswith("demo/") for i in items)  # own copies, viewable by this account
    assert client.get(items[0]["image_url"].replace("http://testserver", ""), headers=h).status_code == 200
    saved = client.get("/outfits?liked_only=true", headers=h).json()
    assert len(saved) == 1 and saved[0]["rating"] == 1 and saved[0]["id"] == outfit["id"]
    own_ids = {i["id"] for i in items}
    assert {i["id"] for i in saved[0]["items"]} <= own_ids and len(saved[0]["items"]) == 3


def test_claim_rejects_bad_tokens_without_creating_an_account(client, auth, fake_ai):
    r = client.post("/auth/register", json={"email": "g@example.com", "password": "supersecret1",
                                            "claim_demo_token": "not-a-token"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_demo_token"
    # A real account's token is not a demo token either.
    real = auth["Authorization"].split()[1]
    r = client.post("/auth/register", json={"email": "g@example.com", "password": "supersecret1",
                                            "claim_demo_token": real})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_demo_token"
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == "g@example.com").count() == 0
    # Claiming twice: the demo account is gone after the first claim.
    token, _, _ = _demo(client, fake_ai)
    assert client.post("/auth/register", json={"email": "h@example.com", "password": "supersecret1",
                                               "claim_demo_token": token}).status_code == 201
    r = client.post("/auth/register", json={"email": "i@example.com", "password": "supersecret1",
                                            "claim_demo_token": token})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_demo_token"
