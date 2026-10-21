"""ai.analysis (AI-06): gap detection and capsule building are deterministic and explainable."""

import random

from app.ai.analysis import CAPSULE_MIN, GAP_CODES, analyze, build_capsule, outfits, pair_ok
from app.ai.context import build_capsule_context
from tests.test_context import ALL, item

W = ("autumn", "winter")
S = ("spring", "summer")


def codes(result):
    return [(g.code, g.category, g.occasion) for g in result.gaps]


def wardrobe():
    """A sensible 10-piece wardrobe: everything casual-to-work, two pairs of shoes, a coat."""
    return [
        item("top", 1, formality=2, colors=("white",)), item("top", 2, formality=3, colors=("navy",)),
        item("top", 3, formality=2, colors=("green",)),
        item("bottom", 4, formality=2, colors=("blue",)), item("bottom", 5, formality=3, colors=("black",)),
        item("dress", 6, formality=3, colors=("burgundy",)),
        item("shoes", 7, formality=2, colors=("white",)), item("shoes", 8, formality=3, colors=("black",)),
        item("outerwear", 9, formality=3, warmth=4, colors=("beige",)),
        item("bag", 10, formality=3, colors=("brown",)),
    ]


# ── compatibility ─────────────────────────────────────────────────────────

def test_pairs_need_close_formality_a_shared_season_and_a_colour_bridge():
    assert pair_ok(item("top", 1, formality=2, colors=("white",)), item("bottom", 2, formality=3, colors=("red",)))
    assert not pair_ok(item("top", 1, formality=1), item("bottom", 2, formality=4))  # lounge + suit trousers
    assert not pair_ok(item("top", 1, seasons=S), item("bottom", 2, seasons=W))
    assert not pair_ok(item("top", 1, colors=("red",)), item("bottom", 2, colors=("green",)))  # no neutral
    assert pair_ok(item("top", 1, colors=("red",)), item("bottom", 2, colors=("red", "white")))  # shared colour


def test_outfits_are_cores_completed_with_fitting_shoes():
    w = wardrobe()
    made = outfits(w)
    assert all(o[-1].category == "shoes" for o in made)
    assert 10 <= len(made) <= 20
    # No shoes at all: the cores count as outfits so the wardrobe is not reported as empty.
    assert all(o[-1].category != "shoes" for o in outfits([i for i in w if i.category != "shoes"]))


# ── gaps ──────────────────────────────────────────────────────────────────

def test_empty_and_healthy_wardrobes():
    empty = analyze([], "autumn")
    assert empty.stats.items == 0 and empty.gaps == ()

    ok = analyze(wardrobe(), "autumn")
    assert ok.stats.per_category == {"top": 3, "bottom": 2, "dress": 1, "shoes": 2, "outerwear": 1, "bag": 1}
    assert ok.stats.outfits_possible == len(outfits(wardrobe()))
    assert 0.3 <= ok.stats.neutral_share <= 0.8
    # Casual + work covered; formal (4-5) and sport (1-2 with a bottom) are not, nothing worse.
    assert all(c in GAP_CODES for c, _, _ in codes(ok))
    assert ("occasion_uncovered", "top", "formal") in codes(ok)
    assert max(g.severity for g in ok.gaps) == 2


def test_missing_core_pieces_are_the_most_severe():
    only_tops = analyze([item("top", 1), item("top", 2)], "summer")
    assert codes(only_tops)[:2] == [("missing_category", "bottom", None), ("missing_category", "shoes", None)]
    assert only_tops.gaps[0].severity == 3

    no_shoes = analyze([item("top", 1), item("bottom", 2)], "summer")
    assert codes(no_shoes)[0] == ("missing_category", "shoes", None)

    dress_only = analyze([item("dress", 1), item("shoes", 2)], "summer")
    assert all(g.code != "missing_category" for g in dress_only.gaps)  # a dress is a complete core


def test_cold_season_without_a_warm_layer_and_summer_only_wardrobe():
    light = [item("top", 1, seasons=S), item("bottom", 2, seasons=S), item("shoes", 3), item("shoes", 4)]
    winter = analyze(light, "winter")
    assert ("season_uncovered", "top", None) in codes(winter)  # nothing for winter at all

    no_coat = [i for i in wardrobe() if i.category != "outerwear"]
    assert ("season_uncovered", "outerwear", None) in codes(analyze(no_coat, "winter"))
    linen = [*no_coat, item("outerwear", 30, warmth=3, seasons=S)]  # a summer jacket doesn't count in winter
    assert ("season_uncovered", "outerwear", None) in codes(analyze(linen, "winter"))
    assert ("season_uncovered", "outerwear", None) not in codes(analyze(no_coat, "summer"))


def test_nice_to_have_gaps():
    one_shoe = [i for i in wardrobe() if i.id != item("shoes", 8).id]
    assert ("few_shoes", "shoes", None) in codes(analyze(one_shoe, "autumn"))

    loud = [item("top", n, colors=("red",)) for n in range(1, 4)] + [item("bottom", n, colors=("red",)) for n in range(4, 7)]
    loud += [item("shoes", 7, colors=("pink",)), item("shoes", 8, colors=("pink",))]
    assert ("low_neutrals", "top", None) in codes(analyze(loud, "autumn"))

    orphan = item("top", 99, formality=5, colors=("gold",))  # black-tie top, nothing to wear it with
    result = analyze([*wardrobe(), orphan], "autumn")
    found = [g for g in result.gaps if g.code == "orphan_items"]
    assert found and found[0].item_ids == (orphan.id,)


def test_gaps_are_sorted_by_severity_then_capped_and_archived_items_ignored():
    result = analyze([item("top", 1, archived=True), item("top", 2)], "summer")
    assert [g.severity for g in result.gaps] == sorted((g.severity for g in result.gaps), reverse=True)
    assert len(result.gaps) <= 8
    assert result.stats.items == 1


# ── capsule ───────────────────────────────────────────────────────────────

def test_capsule_is_deterministic_and_prefers_pieces_that_combine():
    w = wardrobe() + [item("top", 20, formality=5, colors=("gold",)), item("bottom", 21, formality=1, seasons=S)]
    a = build_capsule(w, ("casual", "work"), "autumn", size=8)
    random.seed(1)
    shuffled = w[:]
    random.shuffle(shuffled)
    b = build_capsule(shuffled, ("work", "casual", "work"), "autumn", size=8)
    assert [i.id for i in a.items] == [i.id for i in b.items]
    assert a.occasions == ("casual", "work")
    assert len(a.items) == 8 and a.outfits_possible > 0
    ids = {i.id for i in a.items}
    assert item("top", 20).id not in ids  # outside the casual/work window
    assert item("bottom", 21).id not in ids  # summer piece in autumn
    assert {i.category for i in a.items} >= {"top", "bottom", "shoes"}
    assert a.sample_outfits and all(set(o) <= ids for o in a.sample_outfits)
    assert a.candidates == 10


def test_capsule_size_bounds_and_small_wardrobes():
    few = [item("top", 1), item("bottom", 2), item("shoes", 3)]
    c = build_capsule(few, ("casual",), "spring", size=100)
    assert len(c.items) == 3 and c.outfits_possible == 1
    assert build_capsule([], ("casual",), "spring").items == ()
    big = [item("top", n, colors=("white",)) for n in range(1, 30)] + [item("bottom", n) for n in range(30, 50)]
    big += [item("shoes", 50), item("shoes", 51)]
    assert len(build_capsule(big, ("casual",), "spring", size=3).items) == CAPSULE_MIN
    assert len(build_capsule(big, ("casual",), "spring", size=20).items) == 20


def test_capsule_gaps_only_mention_the_asked_occasions():
    c = build_capsule(wardrobe(), ("casual",), "autumn", size=6)
    assert all(g.occasion in (None, "casual") for g in c.gaps)


def test_capsule_context_names_pieces_by_number_never_by_id():
    c = build_capsule(wardrobe(), ("casual", "work"), "autumn", size=8)
    ctx = build_capsule_context(c)
    assert ctx.text.startswith("CAPSULE for casual, work (autumn): 8 pieces")
    assert "0: " in ctx.text and "EXAMPLE OUTFITS" in ctx.text
    assert not any(str(i.id) in ctx.text for i in c.items)
    assert ctx.item_ids == tuple(i.id for i in c.items)
    assert ctx.estimated_tokens < 600
