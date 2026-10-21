"""Deterministic wardrobe analysis (AI-06): what is missing, and which pieces make the best capsule.

Pure like ai.context: DTOs in, dataclasses out, no DB, no model call, `season` passed in. The results carry
codes and vocabulary values only; the app translates them and the capsule explanation (one LLM call,
features.capsule) is written from these facts, never the other way round.
"""

import uuid
from dataclasses import dataclass
from itertools import product

from ..vocab import CATEGORIES, OCCASION_FORMALITY, OCCASIONS
from .schemas.context import ItemDTO

NEUTRALS = frozenset({"black", "white", "grey", "navy", "beige", "cream", "brown", "khaki"})
COLD_SEASONS = frozenset({"autumn", "winter"})
MAX_GAPS = 8
CAPSULE_MIN, CAPSULE_MAX, CAPSULE_DEFAULT = 6, 20, 12
SAMPLE_OUTFITS = 10
# One top/bottom/dress per category fits; shoes and outerwear can be shared by many outfits.
OCCASION_WEIGHT = {"casual": 3, "work": 3, "formal": 1, "date": 2, "sport": 1, "party": 1, "travel": 2}


@dataclass(frozen=True)
class Gap:
    code: str  # see GAP_CODES
    category: str | None = None  # the piece to add, when the gap is about one category
    occasion: str | None = None
    season: str | None = None
    severity: int = 1  # 3 = can't dress at all, 2 = an occasion is uncovered, 1 = nice to have
    item_ids: tuple[uuid.UUID, ...] = ()  # the pieces the gap is about (orphans)


GAP_CODES = (
    "missing_category",  # no top / bottom-or-dress / shoes at all → severity 3
    "occasion_uncovered",  # no complete outfit inside the occasion's formality window → 2
    "season_uncovered",  # nothing (or no outerwear) for the given season → 2
    "few_shoes",  # one pair of shoes → 1
    "low_neutrals",  # under a third of the pieces have a neutral main colour → 1
    "orphan_items",  # pieces that pair with nothing (formality / season) → 1
    "few_partners",  # a top / bottom / outerwear with only one piece to go with → 1 (one gap per piece)
)
FEW_PARTNERS = 1  # "few" = this many partners or fewer (an orphan has none and is reported above)


@dataclass(frozen=True)
class WardrobeStats:
    items: int
    per_category: dict
    outfits_possible: int  # compatible top+bottom pairs plus dresses
    neutral_share: float


@dataclass(frozen=True)
class Analysis:
    season: str
    stats: WardrobeStats
    gaps: tuple[Gap, ...]


@dataclass(frozen=True)
class Capsule:
    occasions: tuple[str, ...]
    season: str
    items: tuple[ItemDTO, ...]
    outfits_possible: int
    sample_outfits: tuple[tuple[uuid.UUID, ...], ...]
    gaps: tuple[Gap, ...]
    candidates: int = 0  # how many active pieces were considered


# ── compatibility ─────────────────────────────────────────────────────────

def main_color(item: ItemDTO) -> str:
    return item.colors[0] if item.colors else ""


def is_neutral(item: ItemDTO) -> bool:
    return not item.colors or main_color(item) in NEUTRALS


def in_season(item: ItemDTO, season: str) -> bool:
    return not item.seasons or season in item.seasons


def seasons_overlap(a: ItemDTO, b: ItemDTO) -> bool:
    return not a.seasons or not b.seasons or bool(set(a.seasons) & set(b.seasons))


def colors_match(a: ItemDTO, b: ItemDTO) -> bool:
    return is_neutral(a) or is_neutral(b) or bool(set(a.colors) & set(b.colors))


def pair_ok(a: ItemDTO, b: ItemDTO) -> bool:
    """Two garments can be worn together: formality within one step, a common season, harmonious colours."""
    return abs(a.formality - b.formality) <= 1 and seasons_overlap(a, b) and colors_match(a, b)


def shoes_ok(shoe: ItemDTO, pieces: tuple[ItemDTO, ...]) -> bool:
    top_formality = max(p.formality for p in pieces)
    return abs(shoe.formality - top_formality) <= 1 and all(seasons_overlap(shoe, p) for p in pieces)


def _by_category(items) -> dict[str, list[ItemDTO]]:
    out: dict[str, list[ItemDTO]] = {c: [] for c in CATEGORIES}
    for i in items:
        out.setdefault(i.category, []).append(i)
    return out


def cores(items) -> list[tuple[ItemDTO, ...]]:
    """Every wearable core: a compatible (top, bottom) pair or a dress."""
    by = _by_category(items)
    result = [(t, b) for t, b in product(by["top"], by["bottom"]) if pair_ok(t, b)]
    result += [(d,) for d in by["dress"]]
    return result


def outfits(items, known_cores: list[tuple[ItemDTO, ...]] | None = None) -> list[tuple[ItemDTO, ...]]:
    """Cores completed with shoes when the wardrobe has any: the outfits one could actually wear."""
    shoes = _by_category(items)["shoes"]
    result = []
    for core in known_cores if known_cores is not None else cores(items):
        fitting = [s for s in shoes if shoes_ok(s, core)]
        if not shoes:
            result.append(core)
        else:
            result += [(*core, s) for s in fitting]
    return result


def _in_window(item: ItemDTO, occasion: str) -> bool:
    lo, hi = OCCASION_FORMALITY[occasion]
    return lo <= item.formality <= hi


# ── gaps ──────────────────────────────────────────────────────────────────

def _sort_key(item: ItemDTO):
    return (not item.is_favorite, -item.created_at.timestamp(), str(item.id))


def analyze(items: list[ItemDTO], season: str) -> Analysis:
    active = sorted((i for i in items if not i.archived), key=_sort_key)
    by = _by_category(active)
    all_cores = cores(active)  # computed once; the orphan check and the outfit count reuse it
    neutral_share = round(sum(1 for i in active if is_neutral(i)) / len(active), 2) if active else 0.0
    stats = WardrobeStats(items=len(active), per_category={c: len(v) for c, v in by.items() if v},
                          outfits_possible=_count_outfits(all_cores, by["shoes"]), neutral_share=neutral_share)
    gaps: list[Gap] = []

    if not active:
        return Analysis(season=season, stats=stats, gaps=())  # nothing to analyse: onboarding, not gaps

    # 3 — can't make an outfit at all
    if not by["top"] and not by["dress"]:
        gaps.append(Gap("missing_category", category="top", severity=3))
    if not by["bottom"] and not by["dress"]:
        gaps.append(Gap("missing_category", category="bottom", severity=3))
    if not by["shoes"]:
        gaps.append(Gap("missing_category", category="shoes", severity=3))

    # 2 — an occasion has no complete outfit in its formality window
    for occ in OCCASIONS:
        inside = [i for i in active if _in_window(i, occ)]
        if not cores(inside):
            gaps.append(Gap("occasion_uncovered", category=_missing_core(inside), occasion=occ, severity=2))

    # 2 — this season: nothing to wear, or no warm layer in the cold
    in_season_items = [i for i in active if in_season(i, season)]
    if not cores(in_season_items):
        gaps.append(Gap("season_uncovered", category=_missing_core(in_season_items), season=season, severity=2))
    elif season in COLD_SEASONS and not any(i.warmth >= 3 and in_season(i, season) for i in by["outerwear"]):
        gaps.append(Gap("season_uncovered", category="outerwear", season=season, severity=2))

    # 1 — nice to have
    if len(by["shoes"]) == 1:
        gaps.append(Gap("few_shoes", category="shoes", severity=1))
    if len(active) >= 6 and neutral_share < 1 / 3:
        gaps.append(Gap("low_neutrals", category="top" if len(by["top"]) <= len(by["bottom"]) else "bottom", severity=1))
    orphans = tuple(i.id for i in active if i.category in ("top", "bottom", "shoes", "outerwear")
                    and _is_orphan(i, by, all_cores))
    if orphans:
        gaps.append(Gap("orphan_items", severity=1, item_ids=orphans))
    # The progressive nudge: "add a bottom for this jacket" — pieces with one partner, newest first.
    for item in active:
        if item.id in orphans or item.category not in ("top", "bottom", "outerwear"):
            continue
        partners, wanted = _partners(item, by, all_cores)
        if 0 < partners <= FEW_PARTNERS:
            gaps.append(Gap("few_partners", category=wanted, severity=1, item_ids=(item.id,)))

    gaps.sort(key=lambda g: (-g.severity, GAP_CODES.index(g.code), g.occasion or "", g.category or ""))
    return Analysis(season=season, stats=stats, gaps=tuple(gaps[:MAX_GAPS]))


def _missing_core(items: list[ItemDTO]) -> str:
    """Which piece would complete a core here: the absent half of top+bottom, else the one with fewer
    options (the existing tops and bottoms don't pair)."""
    by = _by_category(items)
    if not by["top"]:
        return "top"
    if not by["bottom"]:
        return "bottom"
    return "bottom" if len(by["bottom"]) <= len(by["top"]) else "top"


def _is_orphan(item: ItemDTO, by: dict[str, list[ItemDTO]], all_cores: list[tuple[ItemDTO, ...]]) -> bool:
    if item.category == "top":
        return bool(by["bottom"]) and not any(pair_ok(item, b) for b in by["bottom"])
    if item.category == "bottom":
        return bool(by["top"]) and not any(pair_ok(t, item) for t in by["top"])
    # shoes / outerwear: no core (none of which contains this piece) to go with
    return bool(all_cores) and not any(shoes_ok(item, c) for c in all_cores)


def _partners(item: ItemDTO, by: dict[str, list[ItemDTO]], all_cores: list[tuple[ItemDTO, ...]]) -> tuple[int, str]:
    """How many pieces this one can be worn with, and which category would add more."""
    if item.category == "top":
        return sum(1 for b in by["bottom"] if pair_ok(item, b)), "bottom"
    if item.category == "bottom":
        return sum(1 for t in by["top"] if pair_ok(t, item)), "top"
    fitting = sum(1 for c in all_cores if shoes_ok(item, c))  # outerwear over a core
    return fitting, "bottom" if len(by["bottom"]) <= len(by["top"]) else "top"


def _count_outfits(all_cores: list[tuple[ItemDTO, ...]], shoes: list[ItemDTO]) -> int:
    if not shoes:
        return len(all_cores)
    return sum(sum(1 for s in shoes if shoes_ok(s, c)) for c in all_cores)


# ── capsule ───────────────────────────────────────────────────────────────

def _window(occasions: tuple[str, ...]) -> tuple[int, int]:
    windows = [OCCASION_FORMALITY[o] for o in occasions] or [(1, 5)]
    return min(w[0] for w in windows), max(w[1] for w in windows)


def _score(chosen: list[ItemDTO], occasions: tuple[str, ...], need_shoes: bool) -> float:
    """Outfits the capsule makes, weighted by how many of the asked occasions each one serves. Until the
    capsule has shoes (when the wardrobe has any) a core is only a quarter of an outfit."""
    total = 0.0
    scale = 0.25 if need_shoes and not any(i.category == "shoes" for i in chosen) else 1.0
    for o in outfits(chosen):
        f_lo, f_hi = min(p.formality for p in o), max(p.formality for p in o)
        served = [occ for occ in occasions if OCCASION_FORMALITY[occ][0] <= f_lo and f_hi <= OCCASION_FORMALITY[occ][1]]
        total += (sum(OCCASION_WEIGHT[occ] for occ in served) or 0.5) * scale
    return total


def _potential(cand: ItemDTO, pool: list[ItemDTO]) -> int:
    """How many pieces still in the pool this one could form a core with — a top is worth something before
    its first bottom arrives, otherwise a greedy pick would start with the dress."""
    if cand.category == "top":
        return sum(1 for o in pool if o.category == "bottom" and pair_ok(cand, o))
    if cand.category == "bottom":
        return sum(1 for o in pool if o.category == "top" and pair_ok(o, cand))
    return 0


def build_capsule(items: list[ItemDTO], occasions: tuple[str, ...], season: str,
                  size: int = CAPSULE_DEFAULT) -> Capsule:
    """Greedy: keep adding whichever piece raises the number of wearable outfits most (plus a little for
    pieces that will pair later, a first pair of shoes, a warm layer in the cold, neutrals, favourites).
    Deterministic — ties go to favourites, then the newest piece, then the id."""
    size = max(CAPSULE_MIN, min(CAPSULE_MAX, size))
    occasions = tuple(dict.fromkeys(o for o in occasions if o in OCCASION_FORMALITY)) or ("casual", "work")
    lo, hi = _window(occasions)
    pool = sorted((i for i in items if not i.archived and in_season(i, season) and lo <= i.formality <= hi),
                  key=_sort_key)
    candidates = len(pool)
    need_shoes = any(i.category == "shoes" for i in pool)
    chosen: list[ItemDTO] = []
    cold = season in COLD_SEASONS

    while pool and len(chosen) < size:
        best, best_gain = None, -1.0
        base = _score(chosen, occasions, need_shoes)
        have = _by_category(chosen)
        has_core = bool(cores(chosen))
        for cand in pool:
            gain = _score([*chosen, cand], occasions, need_shoes) - base
            gain += 0.4 * min(_potential(cand, pool), 5)
            if has_core and cand.category == "shoes" and not have["shoes"]:
                gain += 2
            if has_core and cand.category == "outerwear" and cold and not have["outerwear"]:
                gain += 2
            if is_neutral(cand):
                gain += 0.25
            if cand.is_favorite:
                gain += 0.1
            if gain > best_gain:
                best, best_gain = cand, gain
        if best is None or (best_gain <= 0 and len(chosen) >= CAPSULE_MIN):
            break
        chosen.append(best)
        pool.remove(best)

    made = outfits(chosen)
    sample = tuple(tuple(p.id for p in o) for o in made[:SAMPLE_OUTFITS])
    capsule_gaps = tuple(g for g in analyze(chosen, season).gaps
                         if g.occasion is None or g.occasion in occasions)
    return Capsule(occasions=occasions, season=season, items=tuple(chosen), outfits_possible=len(made),
                   sample_outfits=sample, gaps=capsule_gaps, candidates=candidates)


__all__ = ["Analysis", "Capsule", "Gap", "GAP_CODES", "WardrobeStats", "analyze", "build_capsule", "outfits"]
