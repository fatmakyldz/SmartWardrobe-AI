import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from app.db import SessionLocal, engine
from app.models import AIRequest, AIRequestAttempt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ai_report  # noqa: E402


def _req(feature, status, cost, latency, attempts, day=datetime(2026, 10, 18, 9, tzinfo=timezone.utc)):
    r = AIRequest(id=uuid.uuid4(), subject_id=uuid.uuid4(), feature=feature, prompt_version="v1", status=status,
                  input_tokens_total=1000, output_tokens_total=100, cost_usd_micro_total=cost,
                  latency_ms_total=latency, attempts_count=len(attempts), fallback_used=status == "fallback",
                  created_at=day)
    r.attempts = [AIRequestAttempt(attempt_no=n + 1, provider=p, model=m, status=s, error_code=None if s == "ok" else s,
                                   created_at=day) for n, (p, m, s) in enumerate(attempts)]
    return r


def test_report_summarises_yesterday():
    with SessionLocal() as db:
        db.add_all([
            _req("tagging", "ok", 150, 800, [("anthropic", "haiku", "ok")]),
            _req("suggest", "fallback", 4000, 5000, [("anthropic", "sonnet", "timeout"), ("groq", "gpt", "ok")]),
            _req("suggest", "budget", 0, 0, []),
            _req("suggest", "ok", 9999, 1, [("anthropic", "sonnet", "ok")], day=datetime(2026, 10, 17, tzinfo=timezone.utc)),
        ])
        db.commit()
    with engine.connect() as conn:
        text = ai_report.report(conn, date(2026, 10, 18))
    assert "requests 3" in text and "cost $0.0042" in text
    assert "fallback 1 (33.3%)" in text and "budget 1 (33.3%)" in text
    assert "anthropic/sonnet: 1 (timeout 1); failure rate 100.0%" in text
    assert "failure codes: timeout 1" in text
    with engine.connect() as conn:
        assert "No AI requests." in ai_report.report(conn, date(2026, 10, 1))


def test_weekly_report_shows_real_to_estimate_ratio():
    days = [datetime(2026, 10, d, 9, tzinfo=timezone.utc) for d in (12, 15, 18)]
    with SessionLocal() as db:
        for d, est in zip(days, (1000, 1000, None)):  # the last one predates the estimate column
            r = _req("suggest", "ok", 100, 4000, [("anthropic", "sonnet", "ok")], day=d)
            r.estimated_input_tokens = est
            db.add(r)
        budget = _req("suggest", "budget", 0, 0, [], day=days[0])
        budget.estimated_input_tokens = 5000  # never answered: left out of the ratio
        db.add(budget)
        db.commit()
    with engine.connect() as conn:
        text = ai_report.report(conn, date(2026, 10, 12), days=7)
    assert text.startswith("AI report for 2026-10-12 – 2026-10-18 (UTC)") and "requests 4" in text
    assert "suggest: 1.00 over 2 requests" in text  # 2000 real / 2000 estimated
    with engine.connect() as conn:
        assert "requests 1 " in ai_report.report(conn, date(2026, 10, 18))


def test_report_counts_onboarding_ttfo_and_conversion(client, fake_ai, outbox):
    """Two sign-ups yesterday: one saw an outfit after 90 s and verified later, one never did."""
    from datetime import datetime, timedelta, timezone

    from app.db import SessionLocal, engine
    from app.models import Outfit, User
    from scripts.ai_report import report

    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    t0 = datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
    with SessionLocal() as db:
        a = User(email="a@example.com", password_hash="x", created_at=t0, email_verified_at=t0 + timedelta(minutes=30))
        b = User(email="b@example.com", password_hash="x", created_at=t0 + timedelta(hours=1))
        db.add_all([a, b])
        db.flush()
        db.add(Outfit(user_id=a.id, occasion="casual", title="t", reason="r", created_at=t0 + timedelta(seconds=90)))
        db.add(Outfit(user_id=a.id, occasion="casual", title="user", reason="r", source="user",
                      created_at=t0 + timedelta(seconds=10)))  # not an AI outfit: doesn't count
        db.commit()
    with engine.connect() as conn:
        text = report(conn, yesterday)
    assert "onboarding: 2 accounts registered" in text
    assert "first outfit: 1 (50.0%) · time to first outfit p50 90 s · p90 90 s" in text
    assert "verified: 1 (50.0%) · of which after seeing an outfit 1" in text


def test_beta_report_reads_the_cohort_by_day_since_sign_up(client, fake_ai):
    """Two testers: one active on days 0, 1 and 3 with accepted outfits and edited tags, one who signed up and
    vanished. A piece disliked three times that still comes back is counted under AVOID."""
    from datetime import datetime, timedelta, timezone

    from app.db import SessionLocal, engine
    from app.models import FeedbackEvent, Item, Outfit, OutfitItem, User
    from scripts.ai_report import beta_report

    now = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    t0 = now - timedelta(days=3, hours=2)  # tester a signed up 3 days ago
    with SessionLocal() as db:
        a = User(email="A@Example.com", password_hash="x", created_at=t0, email_verified_at=t0 + timedelta(hours=1))
        b = User(email="b@example.com", password_hash="x", created_at=now - timedelta(days=1))
        db.add_all([a, b])
        db.flush()
        raw = {"category": "top", "subcategory": "t-shirt", "colors": ["white"], "pattern": "solid", "warmth": 2, "formality": 2, "seasons": ["summer"]}
        top = Item(user_id=a.id, image_key=f"u/{a.id.hex}/1.webp", category="top", subcategory="shirt", colors=["white"],
                   pattern="solid", warmth=2, formality=3, seasons=["summer"], ai_tags_raw=raw, created_at=t0 + timedelta(minutes=5))
        bottom = Item(user_id=a.id, image_key=f"u/{a.id.hex}/2.webp", category="bottom", colors=["navy"], ai_tags_raw=None,
                      created_at=t0 + timedelta(minutes=6))
        db.add_all([top, bottom])
        db.flush()

        def outfit(at, rating=0, worn=None):
            o = Outfit(user_id=a.id, occasion="casual", title="t", reason="r", source="ai", rating=rating, worn_at=worn, created_at=at,
                       outfit_items=[OutfitItem(item=top, position=0, slot="top"), OutfitItem(item=bottom, position=1, slot="bottom")])
            db.add(o)
            db.flush()
            return o

        o0 = outfit(t0 + timedelta(minutes=10), rating=1)                      # day 0: liked
        outfit(t0 + timedelta(days=1), worn=t0 + timedelta(days=1, hours=1))   # day 1: worn
        d1 = outfit(t0 + timedelta(days=1, hours=2), rating=-1)               # day 1: disliked ×3 (the same pieces)
        d2 = outfit(t0 + timedelta(days=1, hours=3), rating=-1)
        d3 = outfit(t0 + timedelta(days=1, hours=4), rating=-1)
        outfit(t0 + timedelta(days=2))                                        # day 2: the disliked pieces come back
        # a claimed demo brought an older liked outfit along: predates the account, must not count anywhere
        demo_old = Outfit(user_id=a.id, occasion="casual", title="demo", reason="r", source="ai", rating=1, created_at=t0 - timedelta(days=2),
                          outfit_items=[OutfitItem(item=top, position=0, slot="top")])
        db.add(demo_old)
        db.flush()
        events = [(o0, "like", o0.created_at), (d1, "dislike", d1.created_at), (d2, "dislike", d2.created_at), (d3, "dislike", d3.created_at),
                  (demo_old, "like", demo_old.created_at),
                  # dislike → unrate → dislike on one outfit is still one disliked outfit
                  (d3, "unrate", d3.created_at + timedelta(minutes=1)), (d3, "dislike", d3.created_at + timedelta(minutes=2))]
        for o, kind, at in events:
            db.add(FeedbackEvent(user_id=a.id, outfit_id=o.id, kind=kind, created_at=at))
        # colours re-selected in another order are not an edit
        top.colors = ["white"]
        top.ai_tags_raw = {**raw, "colors": ["white"]}
        db.commit()

    with engine.connect() as conn:
        text = beta_report(conn, (now - timedelta(days=5)).date(), now=now)
        only_a = beta_report(conn, (now - timedelta(days=5)).date(), emails=["a@example.com"], now=now)
    assert "2 testers" in text and "1 testers" in only_a
    assert "D1 1/1" in text and "D2 1/1" in text and "D3 -" in text  # b's day 1 and a's day 3 are today: not complete
    assert "acceptance (liked or worn / AI outfits shown): 2/6" in text  # the claimed-demo outfit is not counted
    assert "day 0-1 2/5" in text and "day 2-3 0/1" in text
    assert "worn: 1 tester-days" in text
    assert "pieces per tester p50 0 · p90 2 · total 2" in text
    assert "tag edits before saving: 2 fields over 1 pieces" in text  # subcategory and formality changed
    assert "AVOID: 2 piece(s) disliked 3+ times · suggested again afterwards 2" in text
    assert "verified: 1/2" in text


def test_create_item_keeps_the_raw_ai_tags(client, auth, fake_ai):
    from app.db import SessionLocal
    from app.models import Item
    from tests.test_storage import upload

    fake_ai.respond = lambda call, model: {"is_clothing": True, "category": "top", "colors": ["white"]}
    key = upload(client, auth)
    raw = {"name": "", "category": "top", "subcategory": "", "colors": ["white"], "pattern": "solid", "warmth": 3, "formality": 2, "seasons": []}
    r = client.post("/items", json={**raw, "image_key": key, "subcategory": "shirt", "ai_tags_raw": raw}, headers=auth)
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        item = db.get(Item, __import__("uuid").UUID(r.json()["id"]))
        assert item.subcategory == "shirt" and item.ai_tags_raw["subcategory"] == "" and item.ai_tags_raw["colors"] == ["white"]
