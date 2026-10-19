"""Gateway behaviour with the fake provider (docs/AI-00-foundation.md §4, §12)."""

import json
import logging
import uuid
from dataclasses import dataclass, field

import pytest
from sqlalchemy import select

from app.ai import AIError, AIRequest, complete, routing
from app.ai.providers import FAKE, ImagePart, ProviderError, ProviderResult, TextPart
from app.ai.schemas import TaggingOut
from app.db import SessionLocal
from app.models import AIRequest as AIRequestRow
from app.models import AIRequestAttempt, UsageCounter
from app.vocab import CATEGORIES, COLORS, PATTERNS, SEASONS

TAGS = {"is_clothing": True, "category": "top", "colors": ["red"]}


@dataclass
class Decision:
    allowed: bool = True
    remaining_requests: int | None = None
    remaining_tokens: int = 10_000
    reset_at: str = "2026-10-20T00:00:00Z"


@dataclass
class Gate:
    decision: Decision = field(default_factory=Decision)
    consumed: list[tuple[str, int, bool]] = field(default_factory=list)

    def check(self, feature, estimated_tokens):
        return self.decision

    def consume(self, feature, tokens, succeeded=False):
        self.consumed.append((feature, tokens, succeeded))


def tag_request(**kw) -> AIRequest:
    base = dict(
        feature="tagging", subject_id=uuid.uuid4(), tier="standard", prompt_version="v1",
        system_vars={"categories": CATEGORIES, "colors": COLORS, "patterns": PATTERNS, "seasons": SEASONS,
                     "language": "English"},
        user_content=[TextPart("Catalogue this item."), ImagePart(b"\xff\xd8jpeg")],
        schema=TaggingOut, max_output_tokens=400,
    )
    return AIRequest(**{**base, **kw})


def rows(request_id=None):
    with SessionLocal() as db:
        reqs = db.scalars(select(AIRequestRow)).all()
        atts = db.scalars(select(AIRequestAttempt).order_by(AIRequestAttempt.attempt_no)).all()
        return reqs, atts


def test_success_records_one_request_and_one_attempt():
    FAKE.script("fake-vision-a", TAGS)
    gate = Gate()
    resp = complete(tag_request(), budget=gate)

    assert resp.data.category == "top" and resp.data.colors == ["red"]
    assert (resp.model, resp.model_class, resp.attempts, resp.fallback_used) == ("fake-vision-a", "vision-a", 1, False)
    # fake answers bill 100 in / 50 out; vision-a costs $1 / $5 per MTok = 1 / 5 µ$ per token
    assert (resp.input_tokens, resp.output_tokens, resp.cost_usd_micro) == (100, 50, 350)
    assert gate.consumed == [("tagging", 150, True)]

    reqs, atts = rows()
    assert len(reqs) == 1 and reqs[0].id == resp.request_id
    r = reqs[0]
    assert (r.status, r.final_model, r.attempts_count, r.fallback_used, r.cost_usd_micro_total) == (
        "ok", "fake-vision-a", 1, False, 350)
    assert len(r.prompt_hash) == 64
    assert [(a.attempt_no, a.status, a.model) for a in atts] == [(1, "ok", "fake-vision-a")]


def test_timeout_is_retried_once_on_the_same_model(monkeypatch):
    from app.ai import gateway

    slept = []
    monkeypatch.setattr(gateway, "sleep", slept.append)
    FAKE.script("fake-vision-a", ProviderError("timeout"), TAGS)
    resp = complete(tag_request(), budget=Gate())
    assert (resp.model, resp.attempts, resp.fallback_used) == ("fake-vision-a", 2, False)
    assert slept == [0.5]
    _, atts = rows()
    assert [(a.status, a.error_code) for a in atts] == [("timeout", "timeout"), ("ok", None)]


def test_falls_back_to_the_next_model():
    FAKE.script("fake-vision-a", ProviderError("unavailable", "503"))
    FAKE.script("fake-vision-b", TAGS)
    resp = complete(tag_request(), budget=Gate())
    assert (resp.model, resp.attempts, resp.fallback_used) == ("fake-vision-b", 2, True)
    reqs, atts = rows()
    assert (reqs[0].status, reqs[0].fallback_used, reqs[0].attempts_count) == ("fallback", True, 2)
    assert [(a.model, a.status, a.error_code) for a in atts] == [
        ("fake-vision-a", "error", "unavailable"), ("fake-vision-b", "ok", None)]


def test_auth_error_skips_the_model_without_retry():
    FAKE.script("fake-vision-a", ProviderError("auth", "bad key"))
    FAKE.script("fake-vision-b", TAGS)
    resp = complete(tag_request(), budget=Gate())
    assert resp.model == "fake-vision-b" and [m for m, _ in FAKE.calls] == ["fake-vision-a", "fake-vision-b"]


def test_all_rate_limited_is_ai_busy():
    for m in ("fake-vision-a", "fake-vision-b"):
        FAKE.script(m, ProviderError("rate_limited"), ProviderError("timeout"))
    with pytest.raises(AIError) as e:
        complete(tag_request(), budget=Gate())
    assert (e.value.code, e.value.status) == ("ai_busy", 503)
    reqs, atts = rows()
    assert reqs[0].status == "error" and len(atts) == 4  # 2 candidates × 2 tries


def test_provider_errors_are_ai_unavailable():
    for m in ("fake-vision-a", "fake-vision-b"):
        FAKE.script(m, ProviderError("unavailable"))
    with pytest.raises(AIError) as e:
        complete(tag_request(), budget=Gate())
    assert (e.value.code, e.value.status) == ("ai_unavailable", 503)
    assert len(FAKE.calls) == 2  # 5xx is not retried on the same model


def test_bad_output_is_retried_with_a_repair_note_then_falls_back():
    FAKE.script("fake-vision-a", ProviderError("bad_output"), "not a dict")  # second answer fails the schema
    FAKE.script("fake-vision-b", TAGS)
    resp = complete(tag_request(), budget=Gate())
    assert resp.model == "fake-vision-b" and resp.attempts == 3
    first, second, third = (c for _, c in FAKE.calls)
    assert first.repair_note is None and second.repair_note and third.repair_note is None


def test_bad_output_everywhere_is_ai_bad_reply():
    for m in ("fake-vision-a", "fake-vision-b"):
        FAKE.script(m, ProviderError("bad_output"), ProviderError("bad_output"))
    with pytest.raises(AIError) as e:
        complete(tag_request(), budget=Gate())
    assert (e.value.code, e.value.status) == ("ai_bad_reply", 502)


def test_billed_tokens_of_failed_attempts_are_consumed_request_only_on_success():
    FAKE.script("fake-vision-a", ProviderError("bad_output", input_tokens=300, output_tokens=20),
                ProviderError("timeout"))
    FAKE.script("fake-vision-b", ProviderResult(TAGS, input_tokens=200, output_tokens=40))
    gate = Gate()
    complete(tag_request(), budget=gate)
    assert gate.consumed == [("tagging", 320, False), ("tagging", 0, False), ("tagging", 240, True)]


def test_budget_denied_never_calls_a_provider():
    gate = Gate(Decision(allowed=False, remaining_requests=0, remaining_tokens=1234))
    with pytest.raises(AIError) as e:
        complete(tag_request(), budget=gate)
    assert (e.value.code, e.value.status) == ("budget_exceeded", 429)
    assert e.value.detail == {"reset_at": "2026-10-20T00:00:00Z", "remaining": {"requests": 0, "tokens": 1234}}
    assert FAKE.calls == [] and gate.consumed == []
    reqs, atts = rows()
    assert [r.status for r in reqs] == ["budget"] and atts == []


def test_idempotency_key_reuses_the_answer_for_60_seconds():
    FAKE.respond = lambda call, model: TAGS
    subject = uuid.uuid4()
    first = complete(tag_request(subject_id=subject, idempotency_key="k1"), budget=Gate())
    again = complete(tag_request(subject_id=subject, idempotency_key="k1"), budget=Gate())
    other_key = complete(tag_request(subject_id=subject, idempotency_key="k2"), budget=Gate())
    other_user = complete(tag_request(idempotency_key="k1"), budget=Gate())
    assert again.request_id == first.request_id
    assert len({first.request_id, other_key.request_id, other_user.request_id}) == 3
    assert len(FAKE.calls) == 3


def test_unknown_prompt_version():
    with pytest.raises(AIError) as e:
        complete(tag_request(prompt_version="v9"), budget=Gate())
    assert (e.value.code, e.value.status) == ("prompt_not_found", 500)


def test_no_configured_provider_is_ai_not_configured():
    FAKE.enabled = False
    with pytest.raises(AIError) as e:
        complete(tag_request(), budget=Gate())
    assert (e.value.code, e.value.status) == ("ai_not_configured", 503)


def test_attempt_log_lines_are_json_without_prompt_or_content(caplog):
    FAKE.script("fake-vision-a", TAGS)
    with caplog.at_level(logging.INFO, logger="ai"):
        resp = complete(tag_request(user_content=[TextPart("SECRET USER NOTE")]), budget=Gate())
    lines = [json.loads(r.getMessage()) for r in caplog.records if r.name == "ai"]
    assert len(lines) == 1
    line = lines[0]
    assert {k: line[k] for k in ("ai_request_id", "feature", "provider", "model", "status", "attempt")} == {
        "ai_request_id": str(resp.request_id), "feature": "tagging", "provider": "fake", "model": "fake-vision-a",
        "status": "ok", "attempt": 1}
    assert "latency_ms" in line and line["input_tokens"] == 100
    text = caplog.text
    assert "SECRET USER NOTE" not in text and "catalogue clothing" not in text


def test_circuit_breaker_moves_a_failing_provider_to_the_end(monkeypatch):
    cfg = routing.parse_config({
        "models": {"a": {"provider": "p1", "model": "m1"}, "b": {"provider": "p2", "model": "m2"}},
        "routes": {"tagging": {"standard": ["a", "b"]}},
    })
    monkeypatch.setattr(routing, "config", lambda: cfg)
    health = routing.HEALTH
    assert [c.model for c in routing.chain("tagging", "standard")] == ["m1", "m2"]
    for _ in range(4):
        health.failure("p1", now=100.0)
    assert [c.model for c in routing.chain("tagging", "premium")] == ["m1", "m2"]  # premium falls back to standard
    health.failure("p1", now=100.0)
    assert health.demoted("p1", now=101.0) and not health.demoted("p1", now=100.0 + routing.BREAKER_COOLDOWN_S + 1)
    monkeypatch.setattr(routing.time, "monotonic", lambda: 150.0)
    assert [c.model for c in routing.chain("tagging", "standard")] == ["m2", "m1"]


def test_daily_cap_takes_a_model_out_of_the_chain(monkeypatch):
    cfg = routing.parse_config({
        "models": {"a": {"provider": "p1", "model": "m1"},
                   "b": {"provider": "p2", "model": "m2", "daily_cap_tokens": 1000}},
        "routes": {"tagging": {"standard": ["a", "b"]}},
    })
    monkeypatch.setattr(routing, "config", lambda: cfg)
    routing.HEALTH.add_tokens("b", 999)
    assert [c.model for c in routing.chain("tagging", "standard")] == ["m1", "m2"]
    routing.HEALTH.add_tokens("b", 1)
    assert [c.model for c in routing.chain("tagging", "standard")] == ["m1"]


def test_routes_config_rejects_unknown_model_classes():
    with pytest.raises(ValueError):
        routing.parse_config({"models": {}, "routes": {"tagging": {"standard": ["ghost"]}}})


def test_default_routes_name_no_model_in_code():
    cfg = routing.parse_config(json.loads(routing.DEFAULT_ROUTES.read_text()))
    assert cfg.models["claude-small-vision"].model == "claude-haiku-5-5"
    assert cfg.models["claude-mid"].model == "claude-sonnet-5-5"
    assert [c for c in cfg.routes["tagging"]["standard"]] == ["claude-small-vision", "groq-vision"]
    assert [c for c in cfg.routes["suggest"]["standard"]] == ["claude-mid", "groq-text"]


# ── through the API ─────────────────────────────────────────────────────

def _demo(client):
    token = client.post("/auth/demo", json={}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def good(call, model=None):
    from tests.helpers import outfit

    return {"outfits": [{"title": "t", "items": outfit(call), "reason": "r"}]}


def test_suggest_with_only_invalid_ids_retries_then_succeeds(client):
    h = _demo(client)
    FAKE.script("fake-text-a", {"outfits": [{"title": "x", "items": [999], "reason": "r"}]})
    FAKE.respond = good
    r = client.post("/outfits/suggest", json={}, headers=h)
    assert r.status_code == 200, r.text
    assert FAKE.calls[1][1].repair_note
    outfit_id = r.json()["outfits"][0]["id"]
    with SessionLocal() as db:
        from app.models import Outfit

        o = db.get(Outfit, uuid.UUID(outfit_id))
        req = db.get(AIRequestRow, o.ai_request_id)
        assert (o.prompt_version, req.feature, req.attempts_count) == ("v2", "suggest", 2)


def test_suggest_daily_request_limit_counts_only_successes(client):
    h = _demo(client)  # demo plan: 5 suggestions a day
    FAKE.script("fake-text-a", ProviderError("unavailable"))
    FAKE.script("fake-text-b", ProviderError("unavailable"))
    assert client.post("/outfits/suggest", json={}, headers=h).status_code == 503  # failed: not counted
    FAKE.respond = good
    codes = [client.post("/outfits/suggest", json={}, headers=h).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]
    r = client.post("/outfits/suggest", json={}, headers=h)
    detail = r.json()["detail"]
    assert detail["code"] == "budget_exceeded" and detail["remaining"]["requests"] == 0
    assert detail["reset_at"].endswith("Z")
    with SessionLocal() as db:
        row = db.scalars(select(UsageCounter).where(UsageCounter.feature == "suggest")).one()
        assert row.count == 5 and row.tokens == 5 * 150 + 0  # failed fake errors carry no tokens


def test_tagging_is_not_request_counted_but_spends_tokens(client, auth):
    from tests.test_api import png_bytes

    FAKE.respond = lambda call, model: TAGS
    for n in range(7):  # more than the free plan's 5 requests/day
        r = client.post("/items/analyze", files={"image": ("d.png", png_bytes((n * 35, 100, 0)), "image/png")}, headers=auth)
        assert r.status_code == 200, r.text
    with SessionLocal() as db:
        row = db.scalars(select(UsageCounter)).one()
        assert (row.feature, row.count, row.tokens) == ("tagging", 0, 7 * 150)


def test_token_budget_blocks_any_feature(client, auth):
    from datetime import datetime, timezone

    from app.models import User
    from tests.test_api import png_bytes

    with SessionLocal() as db:
        uid = db.query(User).one().id
        db.add(UsageCounter(user_id=uid, feature="suggest", period_start=datetime.now(timezone.utc).date(),
                            count=0, tokens=39_900))
        db.commit()
    r = client.post("/items/analyze", files={"image": ("d.png", png_bytes(), "image/png")}, headers=auth)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "budget_exceeded"
    assert r.json()["detail"]["remaining"] == {"requests": None, "tokens": 100}
    assert FAKE.calls == []


def test_same_photo_twice_is_tagged_once(client, auth):
    from tests.test_api import png_bytes

    FAKE.respond = lambda call, model: TAGS
    for _ in range(2):
        assert client.post("/items/analyze", files={"image": ("d.png", png_bytes(), "image/png")},
                           headers=auth).status_code == 200
    assert len(FAKE.calls) == 1


def test_suggest_idempotency_key_header(client):
    h = _demo(client)
    FAKE.respond = good
    a = client.post("/outfits/suggest", json={}, headers={**h, "Idempotency-Key": "abc"})
    b = client.post("/outfits/suggest", json={}, headers={**h, "Idempotency-Key": "abc"})
    c = client.post("/outfits/suggest", json={}, headers=h)  # "Suggest again" without a key: a new call
    assert a.status_code == b.status_code == c.status_code == 200
    assert len(FAKE.calls) == 2


def test_ai_debug_log_is_refused_with_postgres():
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {**os.environ, "DATABASE_URL": "postgresql://u:p@localhost:1/x", "SECRET_KEY": "x" * 40,
           "AI_DEBUG_LOG": "true"}
    r = subprocess.run([sys.executable, "-c", "import app.main"], cwd=Path(__file__).resolve().parents[1],
                       env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "AI_DEBUG_LOG" in r.stderr
    env["AI_DEBUG_LOG"] = "false"
    assert subprocess.run([sys.executable, "-c", "import app.main"], cwd=Path(__file__).resolve().parents[1],
                          env=env, capture_output=True).returncode == 0


def test_skipped_models_do_not_hide_a_busy_chain(caplog):
    FAKE.script("fake-vision-a", ProviderError("config", "400 invalid_request_error: unknown field"))
    FAKE.script("fake-vision-b", ProviderError("rate_limited", "429 tokens: slow down"), ProviderError("rate_limited"))
    with caplog.at_level(logging.INFO, logger="ai"), pytest.raises(AIError) as e:
        complete(tag_request(), budget=Gate())
    assert e.value.code == "ai_busy"
    lines = [json.loads(r.getMessage()) for r in caplog.records if r.name == "ai"]
    assert [(l["error_code"], l["detail"]) for l in lines] == [
        ("config", "400 invalid_request_error: unknown field"), ("rate_limited", "429 tokens: slow down"),
        ("rate_limited", None)]


def test_schema_errors_are_logged_without_the_model_output(caplog):
    FAKE.script("fake-vision-a", "SECRET MODEL TEXT", "SECRET MODEL TEXT")
    FAKE.script("fake-vision-b", TAGS)
    with caplog.at_level(logging.INFO, logger="ai"):
        complete(tag_request(), budget=Gate())
    assert "SECRET MODEL TEXT" not in caplog.text and "schema errors" in caplog.text
