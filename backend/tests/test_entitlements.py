"""Plans, the three layers (plan → subscription → grants) and the daily budget (§7)."""

from datetime import date, datetime, timedelta, timezone

from app.db import SessionLocal
from app.entitlements import check_ai_budget, consume, entitlements, period_start
from app.entitlements.service import plans_config, reset_at
from app.models import EntitlementGrant, Subscription, UsageCounter, User

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def _user(db, **kw) -> User:
    kw.setdefault("email_verified_at", NOW)  # verified unless the test says otherwise (C3 (a′))
    u = User(email=f"{len(kw)}-{datetime.now().timestamp()}@example.com", password_hash="x", **kw)
    db.add(u)
    db.commit()
    return u


def _grant(db, user, **kw):
    base = dict(source="support", reason="test", created_by="test", starts_at=NOW - timedelta(days=1))
    db.add(EntitlementGrant(user_id=user.id, **{**base, **kw}))
    db.commit()


def test_plan_values_match_the_design():
    plans = plans_config()["plans"]
    assert {k: (p["max_items"], p["daily_ai_requests"], p["daily_ai_tokens"]) for k, p in plans.items() if k != "unverified"} == {
        "free": (50, 5, 40000), "premium": (300, 60, 600000), "demo": (17, 5, 40000)}
    assert "tagging" not in plans["demo"]["features"]


def test_unverified_accounts_get_the_unverified_plan_and_no_grants():
    with SessionLocal() as db:
        u = _user(db, email_verified_at=None)
        _grant(db, u, plan_override="premium")
        ent = entitlements(u, db, NOW)
        assert (ent.plan, ent.max_items, ent.daily_ai_requests) == ("unverified", 5, 3)
        assert ent.allowed_features == {"tagging", "suggest", "intent"}
        u.email_verified_at = NOW
        db.commit()
        assert entitlements(u, db, NOW).plan == "premium"  # grants apply once verified


def test_base_plan_and_demo():
    with SessionLocal() as db:
        free = entitlements(_user(db), db, NOW)
        assert (free.plan, free.max_items, free.model_tier) == ("free", 50, "standard")
        demo_user = _user(db, is_demo=True, plan="free")  # is_demo wins over a stale plan column
        _grant(db, demo_user, plan_override="premium")  # demo accounts ignore grants
        demo = entitlements(demo_user, db, NOW)
        assert (demo.plan, demo.max_items, "tagging" in demo.allowed_features) == ("demo", 17, False)
        unknown = entitlements(_user(db, plan="gold"), db, NOW)
        assert unknown.plan == "free"


def test_active_subscription_upgrades_expired_one_does_not():
    with SessionLocal() as db:
        u = _user(db)
        db.add(Subscription(user_id=u.id, plan="premium", status="canceled", provider="manual"))
        db.add(Subscription(user_id=u.id, plan="premium", status="active", provider="manual",
                            current_period_end=NOW - timedelta(days=1)))
        db.commit()
        assert entitlements(u, db, NOW).plan == "free"
        db.add(Subscription(user_id=u.id, plan="premium", status="trialing", provider="manual",
                            current_period_end=NOW + timedelta(days=7)))
        db.commit()
        ent = entitlements(u, db, NOW)
        assert (ent.plan, ent.max_items, ent.model_tier, "capsule" in ent.allowed_features) == (
            "premium", 300, "premium", True)


def test_grants_override_add_features_and_raise_limits():
    with SessionLocal() as db:
        u = _user(db)
        _grant(db, u, feature="capsule")
        _grant(db, u, limits={"daily_ai_requests": 20, "max_items": 10, "unknown": 5})  # lower values never shrink
        _grant(db, u, plan_override="premium", ends_at=NOW - timedelta(hours=1))  # expired
        _grant(db, u, plan_override="premium", starts_at=NOW + timedelta(days=1))  # not started
        ent = entitlements(u, db, NOW)
        assert (ent.plan, ent.max_items, ent.daily_ai_requests) == ("free", 50, 20)
        assert "capsule" in ent.allowed_features

        _grant(db, u, plan_override="premium", ends_at=None)
        ent = entitlements(u, db, NOW)
        assert (ent.plan, ent.max_items, ent.daily_ai_requests, ent.model_tier) == ("premium", 300, 60, "premium")


def test_entitlements_only_reads():
    with SessionLocal() as db:
        u = _user(db)
        db.add(Subscription(user_id=u.id, plan="premium", status="active", provider="manual"))
        db.commit()
        entitlements(u, db, NOW)
        assert not db.new and not db.dirty
        assert db.query(Subscription).one().status == "active"


def test_period_follows_the_users_timezone():
    late = datetime(2026, 10, 19, 22, 30, tzinfo=timezone.utc)
    assert period_start(None, late) == date(2026, 10, 19)
    assert period_start("Europe/Istanbul", late) == date(2026, 10, 20)  # UTC+3
    assert period_start("Not/AZone", late) == date(2026, 10, 19)
    assert reset_at("Europe/Istanbul", late) == "2026-10-20T21:00:00Z"
    assert reset_at(None, late) == "2026-10-20T00:00:00Z"


def test_budget_counts_requests_for_suggest_and_tokens_for_everything():
    with SessionLocal() as db:
        u = _user(db)
        ent = entitlements(u, db, NOW)
        consume(db, u.id, "suggest", 1000, 1, now=NOW)
        consume(db, u.id, "suggest", 500, 1, now=NOW)
        consume(db, u.id, "tagging", 2000, 0, now=NOW)
        consume(db, u.id, "suggest", 9999, 1, now=NOW - timedelta(days=1))  # yesterday: ignored
        db.commit()
        assert db.query(UsageCounter).count() == 3  # UPSERT: one row per user/feature/day

        d = check_ai_budget(db, u.id, "suggest", 100, ent, now=NOW)
        assert (d.allowed, d.remaining_requests, d.remaining_tokens) == (True, 3, 40000 - 3500)
        t = check_ai_budget(db, u.id, "tagging", 100, ent, now=NOW)
        assert (t.allowed, t.remaining_requests) == (True, None)
        big = check_ai_budget(db, u.id, "tagging", 40000 - 3500 + 1, ent, now=NOW)
        assert big.allowed is False

        for _ in range(3):
            consume(db, u.id, "suggest", 0, 1, now=NOW)
        db.commit()
        d = check_ai_budget(db, u.id, "suggest", 100, ent, now=NOW)
        assert (d.allowed, d.remaining_requests) == (False, 0)
        assert check_ai_budget(db, u.id, "tagging", 100, ent, now=NOW).allowed is True
