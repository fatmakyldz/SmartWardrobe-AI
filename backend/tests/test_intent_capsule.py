"""AI-06: intent parsing, the request rule in the context, capsule explanation and the three routes.
Invalid model output is coerced or rejected; premium routing goes to the mid model; costs are recorded."""

from datetime import datetime, timezone

import pytest

from app.ai import routing
from app.ai.context import prefilter, request_line
from app.ai.schemas import CapsuleExplainOut, IntentOut
from app.ai.schemas.context import IntentDTO
from app.db import SessionLocal
from app.models import AIRequest, EntitlementGrant, Item, User
from tests.helpers import wardrobe
from tests.test_context import ALL, ctx, item

PARSED = {"occasion": "work", "include_categories": ["outerwear"], "include_colors": ["navy"],
          "avoid_categories": ["dress"], "avoid_colors": [], "avoid_patterns": ["floral"],
          "wants_outerwear": True, "brief": "Warm smart look for a client lunch, no dress."}


# ── schemas ───────────────────────────────────────────────────────────────

def test_intent_out_coerces_to_vocab_and_drops_contradictions():
    out = IntentOut.model_validate({
        "occasion": "Meeting", "include_categories": ["Top", "hat", "top"], "include_colors": ["NAVY", "teal"],
        "avoid_categories": ["top", "dress"], "avoid_colors": ["navy", "red"], "avoid_patterns": ["paisley", "floral"],
        "wants_outerwear": "yes", "brief": "  a   long\n\nbrief " + "x" * 300,
    })
    assert out.occasion is None  # "Meeting" is not in the vocabulary → no override
    assert out.include_categories == ["top"] and out.avoid_categories == ["dress"]  # can't include and avoid
    assert out.include_colors == ["navy"] and out.avoid_colors == ["red"]
    assert out.avoid_patterns == ["floral"] and out.wants_outerwear is None
    assert out.brief.startswith("a long brief") and len(out.brief) == 160
    assert not out.is_empty
    assert IntentOut.model_validate({}).is_empty
    with pytest.raises(ValueError):
        IntentOut.model_validate(["not", "an", "object"])
    schema = IntentOut.tool_schema()
    assert schema["additionalProperties"] is False and "brief" in schema["required"]


def test_capsule_explain_out_needs_a_summary_and_caps_tips():
    out = CapsuleExplainOut.model_validate({"summary": " Two  lines ", "tips": ["a", "", 3, "b " * 200, *"cdefg"]})
    assert out.summary == "Two lines"
    assert len(out.tips) == 5 and out.tips[0] == "a" and out.tips[1] == "3" and len(out.tips[2]) == 180
    with pytest.raises(ValueError):
        CapsuleExplainOut.model_validate({"summary": "", "tips": []})
    assert CapsuleExplainOut.model_validate({"summary": "ok"}).tips == []


# ── context: the request rule ─────────────────────────────────────────────

def test_avoided_pieces_leave_the_context_unless_that_leaves_no_outfit():
    items = [item("top", 1), item("top", 2, colors=("red",)), item("bottom", 3), item("dress", 4),
             item("shoes", 5)]
    intent = IntentDTO(avoid_categories=("dress",), avoid_colors=("red",))
    kept, relaxed = prefilter(items, "casual", None, "autumn", intent=intent)
    assert {i.id for i in kept} == {item("top", 1).id, item("bottom", 3).id, item("shoes", 5).id}
    assert relaxed == ()

    # Only a dress to wear and the user says "no dress": keep it, tell the model instead.
    only_dress = [item("dress", 4), item("shoes", 5)]
    kept, relaxed = prefilter(only_dress, "casual", None, "autumn", intent=IntentDTO(avoid_categories=("dress",)))
    assert len(kept) == 2 and relaxed == ("season", "warmth", "formality", "request")
    c = ctx(only_dress, intent=IntentDTO(avoid_categories=("dress",), brief="no dress please"))
    assert 'REQUEST: user asked for: "no dress please"; avoid dress' in c.text


def test_request_line_and_occasion_override():
    assert request_line(None) is None
    assert request_line(IntentDTO()) is None
    line = request_line(IntentDTO(include_categories=("outerwear",), include_colors=("navy",), wants_outerwear=False,
                                  brief="Smart but warm."))
    assert line == 'REQUEST: user asked for: "Smart but warm."; prefer using outerwear, navy; no outerwear'
    c = ctx([item("top", 1, formality=3), item("bottom", 2, formality=3)], occasion="casual",
            intent=IntentDTO(occasion="work"))
    assert c.text.startswith("OCCASION: work")


# ── routes ────────────────────────────────────────────────────────────────

def _grant(uid, **kw):
    with SessionLocal() as db:
        db.add(EntitlementGrant(user_id=uid, source="support", reason="test", created_by="test",
                                starts_at=datetime(2026, 1, 1, tzinfo=timezone.utc), **kw))
        db.commit()


def _fill_wardrobe(uid, pieces):
    with SessionLocal() as db:
        db.add_all([Item(user_id=uid, image_key=f"u/{uid.hex}/{n}.webp", category=c, colors=list(cols),
                         formality=f, warmth=3, seasons=list(ALL)) for n, (c, cols, f) in enumerate(pieces)])
        db.commit()


def _uid():
    with SessionLocal() as db:
        return db.query(User).one().id


def _ai_rows():
    with SessionLocal() as db:
        return [(r.feature, r.status, r.input_tokens_total + r.output_tokens_total) for r in db.query(AIRequest).all()]


def test_intent_route_parses_and_counts_a_request(client, auth, fake_ai):
    fake_ai.respond = lambda call, model: PARSED
    r = client.post("/outfits/intent", json={"text": "warm smart look for a client lunch, no dress", "lang": "en"},
                    headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["occasion"] == "work" and r.json()["avoid_categories"] == ["dress"]
    model, call = fake_ai.calls[-1]
    assert model == routing.chain("intent", "standard")[0].model
    assert "Request: warm smart look" in call.parts[0].text and "wardrobe app" in call.system
    assert _ai_rows() == [("intent", "ok", 150)]
    assert client.post("/outfits/intent", json={"text": "   "}, headers=auth).status_code == 422


def test_intent_masks_pii_and_honours_the_plan(client, auth, fake_ai):
    seen = []

    def spy(call, model):
        seen.append(call.parts[0].text)
        return PARSED

    fake_ai.respond = spy
    client.post("/outfits/intent", json={"text": "call me on +90 532 123 45 67 or a@b.co"}, headers=auth)
    assert "[phone]" in seen[0] and "[email]" in seen[0] and "532" not in seen[0]

    # Demo accounts may parse intents but not build capsules.
    demo = {"Authorization": f"Bearer {client.post('/auth/demo', json={}).json()['access']}"}
    assert client.post("/outfits/intent", json={"text": "something warm"}, headers=demo).status_code == 200
    r = client.post("/outfits/capsule", json={}, headers=demo)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "feature_not_allowed"


def test_suggest_with_free_text_runs_intent_first(client, fake_weather, fake_ai):
    demo = {"Authorization": f"Bearer {client.post('/auth/demo', json={}).json()['access']}"}
    prompts = []

    def fake_chat(call, model):
        if call.schema_name == "intent":
            return PARSED
        prompts.append(call.parts[0].text)
        w = wardrobe(call)
        assert "dress" not in w  # the avoided category never reaches the stylist
        return {"outfits": [{"title": "Lunch", "items": [w["top"][0], w["bottom"][0], w["shoes"][0]], "reason": "r"}]}

    fake_ai.respond = fake_chat
    r = client.post("/outfits/suggest", json={"occasion": "casual", "request": "warm smart look, no dress"},
                    headers=demo)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"]["occasion"] == "work" and body["outfits"][0]["occasion"] == "work"
    assert prompts[0].startswith("OCCASION: work") and 'REQUEST: user asked for: "Warm smart look' in prompts[0]
    assert [f for f, s, _ in _ai_rows() if s == "ok"] == ["intent", "suggest"]

    # Without free text nothing changes: one request, no intent in the answer.
    r = client.post("/outfits/suggest", json={"occasion": "casual"}, headers=demo)
    assert r.json()["intent"] is None and len(_ai_rows()) == 3


def test_avoided_patterns_and_wanted_outerwear_survive_the_prefilter():
    from app.ai.schemas.context import WeatherDTO

    from dataclasses import replace

    items = [item("top", 1), replace(item("top", 2), pattern="floral"), item("bottom", 3),
             item("outerwear", 4, warmth=4)]
    hot = WeatherDTO(temp=30, feels_like=30)
    kept, _ = prefilter(items, "casual", hot, "summer", intent=IntentDTO(avoid_patterns=("floral",)))
    assert {i.id for i in kept} == {item("top", 1).id, item("bottom", 3).id}  # warm coat and floral top out
    kept, _ = prefilter(items, "casual", hot, "summer", intent=IntentDTO(include_categories=("outerwear",)))
    assert item("outerwear", 4).id in {i.id for i in kept}  # asked for a jacket: the warmth rule steps aside


def test_free_text_suggest_refuses_when_fewer_than_two_requests_remain(client, fake_weather, fake_ai):
    from app.entitlements import consume

    demo = {"Authorization": f"Bearer {client.post('/auth/demo', json={}).json()['access']}"}
    with SessionLocal() as db:
        uid = db.query(User).filter(User.is_demo).one().id
        consume(db, uid, "suggest", tokens=10, requests=4)  # 4 of the demo plan's 5 spent
        db.commit()
    r = client.post("/outfits/suggest", json={"request": "something warm"}, headers=demo)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "budget_exceeded"
    assert fake_ai.calls == [] and _ai_rows() == []  # nothing spent on the parse
    fake_ai.respond = lambda call, model: {"outfits": [{"title": "t", "items": wardrobe(call)["top"][:1] + wardrobe(call)["bottom"][:1], "reason": "r"}]}
    assert client.post("/outfits/suggest", json={}, headers=demo).status_code == 200  # the last plain one


def test_capsule_route_builds_explains_and_routes_premium_to_the_mid_model(client, auth, fake_ai):
    uid = _uid()
    _grant(uid, plan_override="premium")
    _fill_wardrobe(uid, [("top", ("white",), 2), ("top", ("navy",), 3), ("bottom", ("blue",), 2),
                         ("bottom", ("black",), 3), ("shoes", ("white",), 2), ("shoes", ("black",), 3),
                         ("outerwear", ("beige",), 3), ("dress", ("red",), 4)])
    contexts = []

    def explain(call, model):
        contexts.append(call.parts[0].text)
        return {"summary": "A tidy work-ready set.", "tips": ["0 white top + 3 black bottom", "add 6 beige coat"]}

    fake_ai.respond = explain
    r = client.post("/outfits/capsule", json={"occasions": ["work", "casual"], "size": 6, "lang": "en"}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 6 and body["outfits_possible"] >= 4 and body["season"] in ALL
    assert body["summary"] == "A tidy work-ready set." and len(body["tips"]) == 2
    assert all(g["code"] in ("occasion_uncovered", "season_uncovered", "few_shoes", "low_neutrals", "orphan_items")
               for g in body["gaps"])
    assert all(set(o) <= {i["id"] for i in body["items"]} for o in body["sample_outfits"])
    assert contexts[0].startswith("CAPSULE for work, casual")
    model, _ = fake_ai.calls[-1]
    assert model == routing.chain("capsule_explain", "premium")[0].model != routing.chain("capsule_explain", "standard")[0].model
    assert _ai_rows() == [("capsule_explain", "ok", 150)]

    # explain=false: the same capsule, no AI request spent.
    r = client.post("/outfits/capsule", json={"occasions": ["work", "casual"], "size": 6, "explain": False}, headers=auth)
    assert r.json()["summary"] is None and [i["id"] for i in r.json()["items"]] == [i["id"] for i in body["items"]]
    assert len(_ai_rows()) == 1


def test_capsule_needs_pieces_and_a_bad_explanation_is_a_502(client, auth, fake_ai):
    uid = _uid()
    _grant(uid, feature="capsule")
    assert client.post("/outfits/capsule", json={}, headers=auth).json()["detail"]["code"] == "wardrobe_incomplete"
    _fill_wardrobe(uid, [("top", ("white",), 2)] * 8)  # pieces but no outfit: still incomplete, no request spent
    r = client.post("/outfits/capsule", json={"occasions": ["casual"]}, headers=auth)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "wardrobe_incomplete" and fake_ai.calls == []
    assert client.post("/outfits/capsule", json={"occasions": []}, headers=auth).status_code == 422
    _fill_wardrobe(uid, [("bottom", ("blue",), 2)])
    fake_ai.respond = lambda call, model: {"summary": "", "tips": []}
    r = client.post("/outfits/capsule", json={"occasions": ["casual"]}, headers=auth)
    assert r.status_code == 502 and r.json()["detail"]["code"] == "ai_bad_reply"


def test_wardrobe_analysis_route_is_free_for_everyone(client, auth, fake_ai):
    r = client.get("/items/analysis", headers=auth)
    assert r.status_code == 200 and r.json()["items"] == 0 and r.json()["gaps"] == []
    _fill_wardrobe(_uid(), [("top", ("white",), 2), ("top", ("white",), 2)])
    body = client.get("/items/analysis", headers=auth).json()
    assert body["per_category"] == {"top": 2} and body["outfits_possible"] == 0
    assert [g["code"] for g in body["gaps"]][:2] == ["missing_category", "missing_category"]
    assert body["gaps"][0]["severity"] == 3 and body["gaps"][0]["category"] == "bottom"
    demo = {"Authorization": f"Bearer {client.post('/auth/demo', json={}).json()['access']}"}
    demo_body = client.get("/items/analysis", headers=demo).json()
    assert demo_body["items"] == 17 and demo_body["outfits_possible"] > 10
    assert fake_ai.calls == []  # deterministic: never a model call
