"""AI-08: GET /me/entitlements mirrors the budget, and reconcile_usage rewrites counters from ai_requests."""

from datetime import date, datetime, timezone

from app.db import SessionLocal
from app.entitlements.reconcile import reconcile_day
from app.models import AIRequest, UsageCounter, User
from tests.conftest import verify_email
from tests.helpers import answer


def test_entitlements_endpoint_shows_plan_limits_and_todays_usage(client, unverified_auth, fake_ai):
    # Before the e-mail is confirmed: the small plan, plus what confirming unlocks (for the banner).
    u = client.get("/me/entitlements", headers=unverified_auth).json()
    assert u["plan"] == "unverified" and u["verified"] is False and (u["max_items"], u["daily_ai_requests"]) == (5, 3)
    assert u["after_verify"] == {"plan": "free", "max_items": 50, "daily_ai_requests": 5}

    verify_email("fatma@example.com")
    auth = unverified_auth
    r = client.get("/me/entitlements", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan"] == "free" and body["verified"] is True and body["after_verify"] is None
    assert (body["max_items"], body["daily_ai_requests"], body["items_used"]) == (50, 5, 0)
    assert "capsule" not in body["features"] and "user_outfits" in body["features"]
    assert body["usage"] == {"requests_used": 0, "requests_left": 5, "tokens_used": 0, "tokens_left": 40000,
                             "reset_at": body["usage"]["reset_at"]}

    # One suggestion later: 1 used, 4 left, some tokens spent.
    with SessionLocal() as db:
        from app.models import Item

        uid = db.query(User).one().id
        db.add_all([Item(user_id=uid, image_key=f"u/{uid.hex}/{c}.webp", category=c) for c in ("top", "bottom")])
        db.commit()
    fake_ai.respond = answer()
    assert client.post("/outfits/suggest", json={}, headers=auth).status_code == 200
    body = client.get("/me/entitlements", headers=auth).json()
    assert body["usage"]["requests_used"] == 1 and body["usage"]["requests_left"] == 4
    assert body["usage"]["tokens_used"] == 150 and body["items_used"] == 2

    # Reading the endpoint writes nothing.
    with SessionLocal() as db:
        before = (db.query(UsageCounter).count(), db.query(AIRequest).count())
    client.get("/me/entitlements", headers=auth)
    with SessionLocal() as db:
        assert (db.query(UsageCounter).count(), db.query(AIRequest).count()) == before

    # Exhausted: after the plan's daily requests, 0 left and the next suggest is refused.
    for _ in range(4):
        assert client.post("/outfits/suggest", json={}, headers=auth).status_code == 200
    body = client.get("/me/entitlements", headers=auth).json()
    assert (body["usage"]["requests_used"], body["usage"]["requests_left"]) == (5, 0)
    r = client.post("/outfits/suggest", json={}, headers=auth)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "budget_exceeded"

    # Demo and unverified accounts report their own plans.
    demo = {"Authorization": f"Bearer {client.post('/auth/demo', json={}).json()['access']}"}
    d = client.get("/me/entitlements", headers=demo).json()
    assert d["plan"] == "demo" and d["verified"] is True and d["items_used"] == 17 and d["max_items"] == 17


def test_reconcile_rewrites_counters_from_ai_requests():
    today = date(2026, 10, 20)
    with SessionLocal() as db:
        u = User(email="r@example.com", password_hash="x", timezone="Europe/Istanbul", email_verified_at=datetime.now(timezone.utc))
        db.add(u)
        db.flush()
        # Three requests on the user's local Oct 20: two counted successes and one tagging error that still
        # billed its input tokens, plus one at 22:30 UTC Oct 20 = 01:30 local Oct 21 (not this day).
        rows = [("suggest", "ok", 1000, 200, datetime(2026, 10, 20, 9, tzinfo=timezone.utc)),
                ("suggest", "fallback", 900, 100, datetime(2026, 10, 20, 12, tzinfo=timezone.utc)),
                ("tagging", "error", 300, 0, datetime(2026, 10, 19, 22, 30, tzinfo=timezone.utc)),  # 01:30 local Oct 20
                ("suggest", "ok", 5000, 500, datetime(2026, 10, 20, 22, 30, tzinfo=timezone.utc))]  # local Oct 21
        for feature, status, inp, out, at in rows:
            db.add(AIRequest(subject_id=u.id, feature=feature, prompt_version="v1", status=status,
                             input_tokens_total=inp, output_tokens_total=out, created_at=at))
        # Counters drifted: suggest under-counted, tagging missing entirely.
        db.add(UsageCounter(user_id=u.id, feature="suggest", period_start=today, count=1, tokens=1200))
        db.commit()

        drifts = reconcile_day(db, today, apply=False)
        assert {(d.feature, d.counter_count, d.truth_count, d.counter_tokens, d.truth_tokens) for d in drifts} == {
            ("suggest", 1, 2, 1200, 2200), ("tagging", 0, 0, 0, 300)}
        assert all(d.warn for d in drifts)
        assert db.query(UsageCounter).filter_by(feature="tagging").count() == 0  # dry run changed nothing

        reconcile_day(db, today, apply=True)
        db.commit()
        suggest = db.query(UsageCounter).filter_by(user_id=u.id, feature="suggest", period_start=today).one()
        assert (suggest.count, suggest.tokens) == (2, 2200)
        tagging = db.query(UsageCounter).filter_by(user_id=u.id, feature="tagging", period_start=today).one()
        assert (tagging.count, tagging.tokens) == (0, 300)
        assert reconcile_day(db, today, apply=False) == []  # now in agreement


def test_reconcile_falls_back_to_utc_for_missing_or_unknown_timezones():
    day = date(2026, 10, 20)
    with SessionLocal() as db:
        users = [User(email="none@example.com", password_hash="x", timezone=None, email_verified_at=datetime.now(timezone.utc)),
                 User(email="bad@example.com", password_hash="x", timezone="Mars/Olympus", email_verified_at=datetime.now(timezone.utc))]
        db.add_all(users)
        db.flush()
        for u in users:  # 23:30 UTC Oct 20: still Oct 20 in UTC, would be Oct 21 in Istanbul
            db.add(AIRequest(subject_id=u.id, feature="suggest", prompt_version="v1", status="ok",
                             input_tokens_total=100, output_tokens_total=10, created_at=datetime(2026, 10, 20, 23, 30, tzinfo=timezone.utc)))
        db.commit()
        reconcile_day(db, day, apply=True)
        db.commit()
        for u in users:
            row = db.query(UsageCounter).filter_by(user_id=u.id, feature="suggest", period_start=day).one()
            assert (row.count, row.tokens) == (1, 110)


def test_reconcile_script_dry_run_smoke(monkeypatch, capsys):
    import sys

    from scripts import reconcile_usage

    monkeypatch.setattr(sys, "argv", ["reconcile_usage.py", "--dry-run", "--date", "2026-10-20"])
    reconcile_usage.main()
    assert "would fix" in capsys.readouterr().out
