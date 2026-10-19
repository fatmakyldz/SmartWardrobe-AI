"""ai.context: every §6 rule on its own, relaxation order, determinism, PII masking, size bound."""

import random
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.ai.context import build_suggest_context, mask_pii, prefilter, season_of
from app.ai.features.suggest import validate_outfits
from app.ai.schemas import SuggestOut
from app.ai.schemas.context import FeedbackDTO, IntentDTO, ItemDTO, StyleProfileDTO, WeatherDTO

AUTUMN = date(2026, 10, 19)
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
ALL = ("spring", "summer", "autumn", "winter")


def item(category="top", n=0, *, warmth=3, formality=2, seasons=ALL, fav=False, worn=None, archived=False,
         colors=("black",), sub="piece") -> ItemDTO:
    return ItemDTO(id=uuid.UUID(int=n + (hash(category) % 1000) * 10_000), category=category, subcategory=sub,
                   colors=colors, pattern="solid", warmth=warmth, formality=formality, seasons=seasons,
                   created_at=T0 + timedelta(minutes=n), is_favorite=fav, last_worn_at=worn, archived=archived)


def basics(**kw) -> list[ItemDTO]:
    return [item("top", 1, **kw), item("bottom", 2, **kw)]


def ctx(items, weather=None, occasion="casual", note="", **kw):
    args = dict(intent=None, profile=StyleProfileDTO(), summary=None, recent_feedback=[], recently_worn=[], lang="en")
    args.update(kw)
    today = args.pop("today", AUTUMN)
    return build_suggest_context(items, weather, occasion, note, args.pop("intent"), args.pop("profile"),
                                 args.pop("summary"), args.pop("recent_feedback"), args.pop("recently_worn"),
                                 args.pop("lang"), today=today, **args)


def kept(items, **kw):
    return {i.id for i in ctx(items, **kw).items}


# ── step 1: pre-filter ─────────────────────────────────────────────────

def test_archived_items_are_always_out():
    archived_dress = item("dress", 3, archived=True)
    c = ctx([*basics(), archived_dress])
    assert archived_dress.id not in {i.id for i in c.items} and c.items_dropped_count == 1
    # even when relaxing everything would not help
    only_archived = [item("top", 1, archived=True), item("bottom", 2, archived=True)]
    assert ctx(only_archived).items == ()


@pytest.mark.parametrize("today, south, expected", [
    (date(2026, 1, 10), False, "winter"), (date(2026, 4, 1), False, "spring"), (date(2026, 7, 1), False, "summer"),
    (date(2026, 10, 19), False, "autumn"), (date(2026, 10, 19), True, "spring"), (date(2026, 1, 10), True, "summer"),
])
def test_season_of_today(today, south, expected):
    assert season_of(today, south) == expected


def test_season_filter_keeps_items_for_todays_season_or_without_seasons():
    summer_only = item("top", 3, seasons=("summer",))
    no_seasons = item("top", 4, seasons=())
    ids = kept([*basics(), summer_only, no_seasons])
    assert summer_only.id not in ids and no_seasons.id in ids


@pytest.mark.parametrize("feels, warmth, kept_", [
    (25, 4, False), (25, 3, True), (24, 5, True),  # hot: warmth >= 4 out above 24
    (7, 1, False), (7, 2, True), (8, 1, True),  # cold: warmth <= 1 out below 8
])
def test_warmth_follows_feels_like(feels, warmth, kept_):
    piece = item("outerwear", 5, warmth=warmth)
    assert (piece.id in kept([*basics(), piece], weather=WeatherDTO(temp=feels, feels_like=feels))) is kept_


def test_warmth_uses_temp_without_feels_like_and_nothing_without_weather():
    coat = item("outerwear", 5, warmth=5)
    assert coat.id not in kept([*basics(), coat], weather=WeatherDTO(temp=30))
    assert coat.id in kept([*basics(), coat], weather=None)


@pytest.mark.parametrize("occasion, window", [
    ("casual", (1, 3)), ("work", (2, 4)), ("formal", (4, 5)), ("sport", (1, 2)), ("date", (2, 4)),
    ("party", (2, 5)), ("travel", (1, 3)),
])
def test_formality_window_per_occasion(occasion, window):
    lo, hi = window
    # a complete outfit inside the window, plus one shoe at every formality
    base = [item("top", 1, formality=lo), item("bottom", 2, formality=hi)]
    shoes = [item("shoes", 10 + f, formality=f) for f in range(1, 6)]
    c = ctx([*base, *shoes], occasion=occasion)
    assert c.relaxed == ()
    assert sorted(i.formality for i in c.items if i.category == "shoes") == list(range(lo, hi + 1))


def test_category_caps():
    tops = [item("top", n) for n in range(30)]
    bags = [item("bag", 100 + n) for n in range(9)]
    c = ctx([*tops, item("bottom", 200), *bags])
    counts = {cat: sum(1 for i in c.items if i.category == cat) for cat in ("top", "bottom", "bag")}
    assert counts == {"top": 20, "bottom": 1, "bag": 5} and c.items_dropped_count == 14


def test_caps_keep_favourites_and_recently_worn_first():
    old_fav = item("top", 0, fav=True)
    worn = item("top", 1, worn=T0 + timedelta(days=30))
    tops = [item("top", 2 + n) for n in range(25)]
    c = ctx([*tops, worn, old_fav, item("bottom", 99)])
    order = [i.id for i in c.items if i.category == "top"]
    assert order[:2] == [old_fav.id, worn.id] and len(order) == 20


def test_order_is_deterministic():
    items = [item("top", n, fav=n % 7 == 0, worn=(T0 + timedelta(days=n)) if n % 3 == 0 else None) for n in range(15)]
    items += [item("bottom", 50 + n) for n in range(5)]
    first = ctx(items)
    for seed in range(5):
        shuffled = items[:]
        random.Random(seed).shuffle(shuffled)
        assert ctx(shuffled).text == first.text
    tops = [i for i in first.items if i.category == "top"]
    favs = [i for i in tops if i.is_favorite]
    assert tops[: len(favs)] == favs  # favourites first
    worn = [i.last_worn_at for i in tops[len(favs):] if i.last_worn_at]
    assert worn == sorted(worn, reverse=True)  # then most recently worn


# ── relaxation ──────────────────────────────────────────────────────────

def test_relaxes_season_first():
    items = [item("top", 1), item("bottom", 2, seasons=("summer",))]
    c = ctx(items)
    assert c.relaxed == ("season",) and len(c.items) == 2


def test_relaxes_warmth_after_season():
    items = [item("top", 1), item("bottom", 2, warmth=5, seasons=("summer",))]
    c = ctx(items, weather=WeatherDTO(feels_like=30))
    assert c.relaxed == ("season", "warmth") and len(c.items) == 2


def test_relaxes_formality_last():
    items = [item("top", 1, formality=5), item("bottom", 2, formality=5)]
    c = ctx(items, occasion="sport")
    assert c.relaxed == ("season", "warmth", "formality") and len(c.items) == 2


def test_relaxation_only_when_no_complete_outfit():
    # top + shoes is two categories but no outfit: still relaxed (decision in the AI-04 PR)
    items = [item("top", 1), item("shoes", 3), item("bottom", 2, seasons=("summer",))]
    assert ctx(items).relaxed == ("season",)
    dress_alone_is_enough = [item("dress", 1), item("shoes", 2), item("top", 3, seasons=("summer",))]
    assert ctx(dress_alone_is_enough).relaxed == ()


# ── text ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, masked", [
    ("mail me at fatma.k+test@example.com please", "mail me at [email] please"),
    ("call +90 532 123 45 67 tonight", "call [phone] tonight"),
    ("or (0532) 123-4567", "or [phone]"),
    ("05321234567", "[phone]"),
    ("2 shirts, size 38, 2026 event", "2 shirts, size 38, 2026 event"),
])
def test_pii_is_masked(raw, masked):
    assert mask_pii(raw) == masked


def test_note_is_capped_and_masked_in_context():
    c = ctx(basics(), note="x" * 190 + " a@b.co " + "y" * 50)
    line = c.text.splitlines()[0]
    assert "[email]" in line and "a@b.co" not in line and "y" * 10 not in line


def test_intent_occasion_overrides():
    c = ctx(basics(formality=5), occasion="casual", intent=IntentDTO(occasion="formal"))
    assert c.text.startswith("OCCASION: formal") and c.relaxed == ()


def test_index_map_drives_validation():
    items = [item("top", 1), item("bottom", 2), item("shoes", 3)]
    c = ctx(items)
    assert c.index_to_item_id == {n: i.id for n, i in enumerate(c.items)}
    top = next(n for n, i in enumerate(c.items) if i.category == "top")
    bottom = next(n for n, i in enumerate(c.items) if i.category == "bottom")
    out = SuggestOut.model_validate({"outfits": [
        {"title": "ok", "items": [top, bottom, 99], "reason": "r"},
        {"title": "no bottom", "items": [top], "reason": "r"},
    ]})
    valid = validate_outfits(out, c)
    assert [(v.title, [i.id for i in v.items]) for v in valid] == [("ok", [c.items[top].id, c.items[bottom].id])]


def test_snapshot():
    items = [item("top", 1, sub="shirt", colors=("white",)), item("bottom", 2, sub="jeans", colors=("blue",)),
             item("shoes", 3, sub="loafers", formality=3, worn=T0 + timedelta(days=290))]
    c = ctx(
        items, weather=WeatherDTO(temp=12.0, feels_like=10.0, wind_kmh=18.0, code=61, min=9.0, max=14.0, rain_chance=70),
        occasion="work", note="meeting, ring me on 0532 111 22 33",
        profile=StyleProfileDTO(styles=("minimal",), palettes=("dark",), priority="comfort", liked_colors=("navy",),
                                disliked_colors=("pink",), avoid=("floral",)),
        summary="Likes black and navy pieces. Leans smart-casual.",
        recent_feedback=[FeedbackDTO("like", (("top", "white"), ("bottom", "blue"))), FeedbackDTO("dislike", ())],
        recently_worn=[items[2].id],
    )
    assert c.text == """OCCASION: work — user note: meeting, ring me on [phone]
WEATHER: now 12.0°C (feels 10.0°C), today 9.0–14.0°C, rain, rain chance 70%, wind 18.0 km/h (season: autumn)
STYLE: prefers style minimal; palette dark; likes colours navy; priority comfort
AVOID: pink, floral
TASTE SUMMARY: Likes black and navy pieces. Leans smart-casual.
RECENT FEEDBACK (newest first, by category and colour): like [top white + bottom blue]
RECENTLY WORN (last 7 days, prefer variety): [0]
WARDROBE (id: category/type | attributes):
0: shoes/loafers | colors=black | pattern=solid | warmth=3 | formality=3 | seasons=all
1: bottom/jeans | colors=blue | pattern=solid | warmth=3 | formality=2 | seasons=all
2: top/shirt | colors=white | pattern=solid | warmth=3 | formality=2 | seasons=all"""
    assert c.estimated_tokens == len(c.text) // 4


def test_recent_feedback_shows_at_most_five():
    fb = [FeedbackDTO("like", (("top", str(n)),)) for n in range(8)]
    line = next(l for l in ctx(basics(), recent_feedback=fb).text.splitlines() if l.startswith("RECENT"))
    assert line.count("like [") == 5


def test_three_hundred_piece_wardrobe_stays_under_budget():
    rnd = random.Random(1)
    cats = ["top"] * 90 + ["bottom"] * 60 + ["dress"] * 30 + ["outerwear"] * 35 + ["shoes"] * 40 + ["bag"] * 20 + \
        ["accessory"] * 25
    subs = ["t-shirt", "chelsea boots", "midi dress", "wide-leg trousers", "leather jacket", "crossbody bag"]
    items = [item(c, n, warmth=rnd.randint(1, 5), formality=rnd.randint(1, 5), sub=rnd.choice(subs),
                  colors=tuple(rnd.sample(["black", "white", "navy", "beige", "olive"], 3)),
                  seasons=tuple(rnd.sample(ALL, rnd.randint(1, 4)))) for n, c in enumerate(cats)]
    fb = [FeedbackDTO("like", (("top", "black"), ("bottom", "navy"), ("shoes", "white")))] * 5
    c = ctx(items, weather=WeatherDTO(temp=12, feels_like=10, code=61), note="n" * 200, recent_feedback=fb,
            summary="s" * 320, profile=StyleProfileDTO(styles=("minimal", "classic"), liked_colors=("navy",) * 8))
    assert len(c.items) <= 69 and c.estimated_tokens <= 2500


def test_prefilter_is_pure():
    items = basics()
    before = list(items)
    prefilter(items, "casual", None, "autumn")
    assert items == before
