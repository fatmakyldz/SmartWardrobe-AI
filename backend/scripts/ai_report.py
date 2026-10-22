"""AI summary from ai_requests / ai_request_attempts: cost, tokens and latency by feature,
fallback / error / budget rates, failures by provider, and how the budget's input estimate compares
with the real input tokens. Plus onboarding: time to first outfit (sign-up → first AI outfit) and
unverified → verified conversion for the accounts registered in the period. Read-only.

    python scripts/ai_report.py                          # yesterday (UTC)
    python scripts/ai_report.py --date 2026-10-19
    python scripts/ai_report.py --days 7                 # the 7 days up to yesterday (weekly)
    python scripts/ai_report.py --beta 2026-10-27        # the closed-beta cohort: accounts registered since that
                                                         # day, by day since sign-up (retention, acceptance, worn,
                                                         # tag edits, pieces) — the beta plan's metrics
    python scripts/ai_report.py --beta 2026-10-27 --emails a@x.com,b@x.com   # only these testers
"""

import argparse
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import AIRequest, AIRequestAttempt, FeedbackEvent, Item, Outfit, OutfitItem, User  # noqa: E402


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "-"


def _p(values: list[int], q: float) -> int:
    if not values:
        return 0
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def report(conn: sa.Connection, day: date, days: int = 1) -> str:
    """Covers [day, day + days)."""
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=days)
    reqs = conn.execute(sa.select(AIRequest.__table__).where(AIRequest.created_at >= start,
                                                             AIRequest.created_at < end)).all()
    atts = conn.execute(
        sa.select(AIRequestAttempt.__table__)
        .join(AIRequest.__table__, AIRequestAttempt.request_id == AIRequest.id)
        .where(AIRequest.created_at >= start, AIRequest.created_at < end)
    ).all()

    period = day.isoformat() if days == 1 else f"{day.isoformat()} – {(day + timedelta(days=days - 1)).isoformat()}"
    lines = [f"AI report for {period} (UTC)", ""]
    onboarding = onboarding_lines(conn, start, end)
    if not reqs:
        return "\n".join(lines + ["No AI requests.", "", *onboarding])

    statuses = Counter(r.status for r in reqs)
    cost = sum(r.cost_usd_micro_total for r in reqs) / 1_000_000
    users = len({r.subject_id for r in reqs if r.subject_id})
    lines += [
        f"requests {len(reqs)} · users {users} · cost ${cost:.4f}",
        f"ok {statuses['ok']} · fallback {statuses['fallback']} ({_pct(statuses['fallback'], len(reqs))})"
        f" · error {statuses['error']} ({_pct(statuses['error'], len(reqs))})"
        f" · budget {statuses['budget']} ({_pct(statuses['budget'], len(reqs))})",
        "",
        f"{'feature':<16}{'requests':>9}{'cost $':>10}{'in tok':>10}{'out tok':>10}{'p50 ms':>9}{'p95 ms':>9}",
    ]
    by_feature = defaultdict(list)
    for r in reqs:
        by_feature[r.feature].append(r)
    for feature, rows in sorted(by_feature.items()):
        lat = [r.latency_ms_total for r in rows if r.status in ("ok", "fallback")]
        lines.append(
            f"{feature:<16}{len(rows):>9}{sum(r.cost_usd_micro_total for r in rows) / 1e6:>10.4f}"
            f"{sum(r.input_tokens_total for r in rows):>10}{sum(r.output_tokens_total for r in rows):>10}"
            f"{_p(lat, 0.5):>9}{_p(lat, 0.95):>9}"
        )

    lines += ["", "input tokens: real / budget estimate (answered requests with an estimate):"]
    for feature, rows in sorted(by_feature.items()):
        est = [r for r in rows if r.estimated_input_tokens and r.status in ("ok", "fallback")]
        if est:
            ratio = sum(r.input_tokens_total for r in est) / sum(r.estimated_input_tokens for r in est)
            lines.append(f"  {feature}: {ratio:.2f} over {len(est)} requests "
                         f"(< 1: estimate too high; > 1: too low, raise TEXT_TOKEN_FACTOR)")
        else:
            lines.append(f"  {feature}: -")

    lines += ["", "attempts by model:"]
    by_model = defaultdict(Counter)
    for a in atts:
        by_model[(a.provider, a.model)][a.status] += 1
    for (provider, model), counts in sorted(by_model.items()):
        total = sum(counts.values())
        detail = ", ".join(f"{s} {n}" for s, n in sorted(counts.items()))
        lines.append(f"  {provider}/{model}: {total} ({detail}); failure rate {_pct(total - counts['ok'], total)}")

    errors = Counter(a.error_code for a in atts if a.status != "ok")
    if errors:
        lines += ["", "failure codes: " + ", ".join(f"{c} {n}" for c, n in errors.most_common())]
    if lat_all := [r.latency_ms_total for r in reqs if r.status in ("ok", "fallback")]:
        lines += ["", f"mean latency {statistics.mean(lat_all):.0f} ms"]
    lines += ["", *onboarding]
    return "\n".join(lines)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def onboarding_lines(conn: sa.Connection, start: datetime, end: datetime) -> list[str]:
    """Accounts registered in the period: how many saw a first AI outfit and how fast (median / p90
    seconds from sign-up), how many confirmed their email (C3 (a′): the unverified → verified
    conversion). Demo accounts are left out; the clock starts at users.created_at."""
    users = conn.execute(
        sa.select(User.id, User.created_at, User.email_verified_at)
        .where(User.created_at >= start, User.created_at < end, User.is_demo.is_(False))
    ).all()
    lines = [f"onboarding: {len(users)} accounts registered"]
    if not users:
        return lines
    ids = [u.id for u in users]
    # AI outfits only (an edited suggestion still counts); outfits older than the account are the ones a
    # claimed demo brought along and don't count as the account's first.
    first = dict(
        conn.execute(
            sa.select(Outfit.user_id, sa.func.min(Outfit.created_at))
            .join(User, User.id == Outfit.user_id)
            .where(Outfit.user_id.in_(ids), Outfit.source.in_(("ai", "ai_edited")), Outfit.created_at >= User.created_at)
            .group_by(Outfit.user_id)
        ).all()
    )
    ttfo = [int((_aware(first[u.id]) - _aware(u.created_at)).total_seconds()) for u in users if u.id in first]
    verified = sum(1 for u in users if u.email_verified_at is not None)
    verified_after_outfit = sum(
        1 for u in users if u.email_verified_at is not None and u.id in first and _aware(u.email_verified_at) >= _aware(first[u.id])
    )
    lines.append(f"  first outfit: {len(ttfo)} ({_pct(len(ttfo), len(users))})"
                 + (f" · time to first outfit p50 {_p(ttfo, 0.5)} s · p90 {_p(ttfo, 0.9)} s" if ttfo else ""))
    lines.append(f"  verified: {verified} ({_pct(verified, len(users))}) · of which after seeing an outfit "
                 f"{verified_after_outfit}")
    return lines


TAG_FIELDS = ("category", "subcategory", "colors", "pattern", "warmth", "formality", "seasons")


def beta_report(conn: sa.Connection, since: date, emails: list[str] | None = None, days: int = 7,
                now: datetime | None = None) -> str:
    """The closed beta, read by day since each tester's sign-up (day 0 = the sign-up day), so testers who
    joined on different dates line up. Everything comes from server records: no survey.

    - active: any of an AI request, an item added, an outfit created, a rating or a worn mark that day
    - acceptance: AI outfits created that day that were liked or worn (rating 1 or worn_at) / AI outfits shown
    - worn: days with a worn outfit / active days
    - tag edits: fields the person changed before saving, against ai_tags_raw (pieces with raw tags only)
    - AVOID: pieces disliked in 3+ distinct outfits that still appear in a later AI outfit (not ai_edited: the
      person may have put the piece back themselves)

    Days are UTC dates. Records older than the account (a claimed demo's outfits, feedback and requests) are
    skipped; copied demo pieces still count in "pieces per tester". Retention counts completed days only; the
    acceptance of an outfit is read as its latest state (a like withdrawn later is not an acceptance).
    """
    now = now or datetime.now(timezone.utc)
    start = datetime.combine(since, time.min, tzinfo=timezone.utc)
    q = sa.select(User.id, User.email, User.created_at, User.email_verified_at).where(
        User.created_at >= start, User.is_demo.is_(False))
    if emails:
        q = q.where(sa.func.lower(User.email).in_([e.strip().lower() for e in emails if e.strip()]))
    users = conn.execute(q).all()
    lines = [f"beta cohort since {since} (UTC days): {len(users)} testers"]
    if not users:
        return "\n".join(lines)
    ids = [u.id for u in users]
    created = {u.id: _aware(u.created_at) for u in users}

    def day_of(uid, at) -> int:
        return (_aware(at).date() - created[uid].date()).days

    active: dict = defaultdict(set)  # user -> {day}

    def mark(uid, at) -> None:
        d = day_of(uid, at)
        if d >= 0:  # claimed-demo records predate the account
            active[uid].add(d)

    for uid, at in conn.execute(sa.select(AIRequest.subject_id, AIRequest.created_at).where(AIRequest.subject_id.in_(ids))):
        mark(uid, at)
    items = conn.execute(sa.select(Item.id, Item.user_id, Item.created_at, Item.ai_tags_raw, Item.category, Item.subcategory,
                                   Item.colors, Item.pattern, Item.warmth, Item.formality, Item.seasons)
                         .where(Item.user_id.in_(ids))).all()
    for it in items:
        mark(it.user_id, it.created_at)
    outfits = [o for o in conn.execute(
        sa.select(Outfit.id, Outfit.user_id, Outfit.created_at, Outfit.source, Outfit.rating, Outfit.worn_at)
        .where(Outfit.user_id.in_(ids))).all() if day_of(o.user_id, o.created_at) >= 0]
    for o in outfits:
        mark(o.user_id, o.created_at)
        if o.worn_at:
            mark(o.user_id, o.worn_at)
    for uid, at in conn.execute(sa.select(FeedbackEvent.user_id, FeedbackEvent.created_at).where(FeedbackEvent.user_id.in_(ids))):
        mark(uid, at)

    # retention by day since sign-up, over testers whose day d is complete (today is partial)
    horizon = {u.id: (now.date() - created[u.id].date()).days for u in users}
    ret = []
    for d in range(1, days + 1):
        eligible = [u.id for u in users if horizon[u.id] > d]
        hit = sum(1 for uid in eligible if d in active[uid])
        ret.append(f"D{d} {hit}/{len(eligible)}" if eligible else f"D{d} -")
    lines.append("  active by day since sign-up: " + " · ".join(ret))

    # acceptance per day bucket (AI outfits only)
    shown: Counter = Counter()
    accepted: Counter = Counter()
    for o in outfits:
        if o.source not in ("ai", "ai_edited"):
            continue
        d = day_of(o.user_id, o.created_at)
        shown[d] += 1
        if o.rating == 1 or o.worn_at is not None:
            accepted[d] += 1
    buckets = [("day 0-1", range(0, 2)), ("day 2-3", range(2, 4)), ("day 4-5", range(4, 6)), ("day 6-7", range(6, 8))]
    parts = []
    for name, rng in buckets:
        sh = sum(shown[d] for d in rng)
        ac = sum(accepted[d] for d in rng)
        parts.append(f"{name} {ac}/{sh} ({_pct(ac, sh)})")
    total_shown, total_acc = sum(shown.values()), sum(accepted.values())
    lines.append(f"  acceptance (liked or worn / AI outfits shown): {total_acc}/{total_shown} ({_pct(total_acc, total_shown)}) — "
                 + " · ".join(parts))

    worn_days = len({(o.user_id, day_of(o.user_id, o.worn_at)) for o in outfits if o.worn_at})
    active_days = sum(len(v) for v in active.values())
    lines.append(f"  worn: {worn_days} tester-days with a worn outfit / {active_days} active tester-days ({_pct(worn_days, active_days)})")

    # pieces and tag edits
    per_user = Counter(it.user_id for it in items)
    counts = sorted(per_user.get(u.id, 0) for u in users)
    edits, with_raw = 0, 0
    for it in items:
        raw = it.ai_tags_raw or {}
        if not raw:
            continue
        with_raw += 1
        for f in TAG_FIELDS:
            if f not in raw:
                continue
            a, b = raw[f], getattr(it, f)
            if isinstance(a, list) and isinstance(b, list):
                a, b = sorted(map(str, a)), sorted(map(str, b))  # the editor re-appends a re-selected colour
            if a != b:
                edits += 1
    lines.append(f"  pieces per tester p50 {_p(counts, 0.5)} · p90 {_p(counts, 0.9)} · total {len(items)}")
    lines.append(f"  tag edits before saving: {edits} fields over {with_raw} pieces with raw tags "
                 f"({edits / with_raw:.2f} per piece)" if with_raw else "  tag edits: no pieces carry ai_tags_raw yet")

    # AVOID: disliked in 3+ distinct outfits (the earliest dislike per outfit; dislike → unrate → dislike on one
    # outfit is one), suggested again afterwards
    dislikes = conn.execute(
        sa.select(OutfitItem.item_id, Outfit.user_id, Outfit.id, Outfit.created_at, FeedbackEvent.created_at)
        .join(Outfit, Outfit.id == OutfitItem.outfit_id)
        .join(FeedbackEvent, FeedbackEvent.outfit_id == Outfit.id)
        .where(Outfit.user_id.in_(ids), FeedbackEvent.kind == "dislike")
    ).all()
    third: dict = {}
    by_item: dict = defaultdict(dict)  # (user, item) -> {outfit: earliest dislike}
    for item_id, uid, outfit_id, o_created, at in dislikes:
        if day_of(uid, o_created) < 0:
            continue
        at = _aware(at)
        prev = by_item[(uid, item_id)].get(outfit_id)
        by_item[(uid, item_id)][outfit_id] = at if prev is None or at < prev else prev
    for key, per_outfit in by_item.items():
        if len(per_outfit) >= 3:
            third[key] = sorted(per_outfit.values())[2]
    resuggested = 0
    if third:
        later = conn.execute(
            sa.select(OutfitItem.item_id, Outfit.user_id, Outfit.created_at)
            .join(Outfit, Outfit.id == OutfitItem.outfit_id)
            .where(Outfit.user_id.in_(ids), Outfit.source == "ai")
        ).all()
        resuggested = sum(1 for item_id, uid, at in later if (uid, item_id) in third and _aware(at) > third[(uid, item_id)])
    lines.append(f"  AVOID: {len(third)} piece(s) disliked 3+ times · suggested again afterwards {resuggested}")
    verified = sum(1 for u in users if u.email_verified_at is not None)
    lines.append(f"  verified: {verified}/{len(users)}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--date", type=date.fromisoformat, help="last day of the period (default: yesterday)",
                        default=datetime.now(timezone.utc).date() - timedelta(days=1))
    parser.add_argument("--days", type=int, default=1, help="period length in days, e.g. 7 for a weekly report")
    parser.add_argument("--beta", type=date.fromisoformat, metavar="SINCE",
                        help="closed-beta report for accounts registered since this day (instead of the AI summary)")
    parser.add_argument("--emails", help="comma-separated tester e-mails to restrict --beta to")
    args = parser.parse_args()

    from app.db import engine

    with engine.connect() as conn:
        if args.beta:
            print(beta_report(conn, args.beta, args.emails.split(",") if args.emails else None))
        else:
            print(report(conn, args.date - timedelta(days=args.days - 1), args.days))


if __name__ == "__main__":
    main()
