"""Builds what the model sees for a suggestion (docs/AI-00-foundation.md §6).

Pure: DTOs in, a DTO out. No DB, no network, no clock — `today` is a parameter — so the same input
always gives the same text and the rules are snapshot-testable.
"""

import re
from datetime import date

from ..vocab import OCCASION_FORMALITY
from ..weather import describe
from .schemas.context import (
    DEFAULT_LIMITS,
    CapsuleContext,
    ContextLimits,
    FeedbackDTO,
    IntentDTO,
    ItemDTO,
    StyleProfileDTO,
    SuggestContext,
    WeatherDTO,
)

RELAX_ORDER = ("season", "warmth", "formality")
# A parsed request's avoid-lists are a 4th rule, relaxed only after the weather and occasion rules:
# "no dress" is the clearest signal the user gave.
REQUEST_RULE = "request"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\w(])[+(]?\d[\d\s().-]{6,}\d(?!\w)")


def season_of(today: date, southern_hemisphere: bool = False) -> str:
    seasons = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
               6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}
    s = seasons[today.month]
    if southern_hemisphere:
        s = {"winter": "summer", "summer": "winter", "spring": "autumn", "autumn": "spring"}[s]
    return s


def mask_pii(text: str) -> str:
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text))


def _sort_key(item: ItemDTO):
    # is_favorite desc, last_worn_at desc nulls last, created_at desc, id
    worn = item.last_worn_at
    return (
        not item.is_favorite,
        worn is None,
        -worn.timestamp() if worn else 0,
        -item.created_at.timestamp(),
        str(item.id),
    )


def _complete(items: list[ItemDTO]) -> bool:
    cats = {i.category for i in items}
    return len(cats) >= 2 and ("dress" in cats or {"top", "bottom"} <= cats)


def _avoided(item: ItemDTO, intent: IntentDTO | None) -> bool:
    if intent is None:
        return False
    return (
        item.category in intent.avoid_categories
        or item.pattern in intent.avoid_patterns
        or bool(set(item.colors) & set(intent.avoid_colors))
    )


def _passes(item: ItemDTO, rule: str, season: str, feels: float | None, window: tuple[int, int],
            limits: ContextLimits, intent: IntentDTO | None = None) -> bool:
    if rule == REQUEST_RULE:
        return not _avoided(item, intent)
    if rule == "season":
        return not item.seasons or season in item.seasons
    if rule == "warmth":
        if feels is None:
            return True
        if feels > limits.hot_feels_like and item.warmth >= 4:
            return False
        if feels < limits.cold_feels_like and item.warmth <= 1:
            return False
        return True
    lo, hi = window
    return lo <= item.formality <= hi


def prefilter(items: list[ItemDTO], occasion: str, weather: WeatherDTO | None, season: str,
              limits: ContextLimits = DEFAULT_LIMITS, intent: IntentDTO | None = None,
              ) -> tuple[list[ItemDTO], tuple[str, ...]]:
    """§6 step 1. Returns the kept items in final order and the filters that had to be relaxed."""
    active = [i for i in items if not i.archived]
    feels = None
    if weather is not None:
        feels = weather.feels_like if weather.feels_like is not None else weather.temp
    window = OCCASION_FORMALITY.get(occasion, (1, 5))

    rules = list(RELAX_ORDER)
    if intent is not None and intent.has_avoids:
        rules.append(REQUEST_RULE)
    relaxed: list[str] = []
    while True:
        kept = [i for i in active if all(_passes(i, r, season, feels, window, limits, intent) for r in rules)]
        if _complete(kept) or not rules:
            break
        relaxed.append(rules.pop(0))  # season → warmth → formality

    kept.sort(key=_sort_key)
    per_category: dict[str, int] = {}
    capped = []
    for item in kept:
        cap = limits.category_caps.get(item.category, 8)
        if per_category.get(item.category, 0) < cap:
            per_category[item.category] = per_category.get(item.category, 0) + 1
            capped.append(item)
    return capped, tuple(relaxed)


def item_line(i: int, item: ItemDTO) -> str:
    return (
        f"{i}: {item.category}/{item.subcategory or '-'} | colors={','.join(item.colors) or '-'} "
        f"| pattern={item.pattern} | warmth={item.warmth} | formality={item.formality} "
        f"| seasons={_seasons(item.seasons)}"
    )


def _seasons(seasons) -> str:
    if not seasons or set(seasons) >= {"spring", "summer", "autumn", "winter"}:
        return "all"  # most pieces; saves ~6 tokens a line
    return ",".join(seasons)


def weather_line(w: WeatherDTO | None, season: str) -> str:
    if w is None:
        return f"WEATHER: unknown, assume mild indoor day (season: {season})"
    return (
        f"WEATHER: now {w.temp}°C (feels {w.feels_like}°C), today {w.min}–{w.max}°C, "
        f"{describe(w.code)}, rain chance {w.rain_chance}%, wind {w.wind_kmh} km/h (season: {season})"
    )


def style_lines(p: StyleProfileDTO) -> list[str]:
    parts = []
    if p.styles:
        parts.append(f"style {', '.join(p.styles)}")
    if p.palettes:
        parts.append(f"palette {', '.join(p.palettes)}")
    if p.liked_colors:
        parts.append(f"likes colours {', '.join(p.liked_colors)}")
    if p.priority:
        parts.append(f"priority {p.priority}")
    avoid = [*p.disliked_colors, *p.avoid]
    lines = [f"STYLE: prefers {'; '.join(parts)}"] if parts else []
    if avoid:
        lines.append(f"AVOID: {', '.join(avoid)}")
    return lines


def request_line(intent: IntentDTO | None, avoids_relaxed: bool = False) -> str | None:
    """The parsed request as one line. Avoided pieces are normally already filtered out; when the filter had
    to be relaxed to keep an outfit possible, the model is told to steer clear of them instead."""
    if intent is None:
        return None
    parts = []
    if intent.brief:
        parts.append(intent.brief)
    if intent.include_categories or intent.include_colors:
        parts.append("must use " + ", ".join([*intent.include_categories, *intent.include_colors]))
    if intent.wants_outerwear is True:
        parts.append("add outerwear")
    elif intent.wants_outerwear is False:
        parts.append("no outerwear")
    if avoids_relaxed and intent.has_avoids:
        parts.append("avoid " + ", ".join([*intent.avoid_categories, *intent.avoid_colors, *intent.avoid_patterns]))
    return "REQUEST: " + "; ".join(parts) if parts else None


def feedback_line(events: list[FeedbackDTO], limit: int) -> str | None:
    shown = [e for e in events if e.pieces][:limit]
    if not shown:
        return None
    sigs = [f"{e.kind} [{' + '.join(f'{c} {col}'.strip() for c, col in e.pieces)}]" for e in shown]
    return "RECENT FEEDBACK (newest first, by category and colour): " + "; ".join(sigs)


def build_suggest_context(
    items: list[ItemDTO],
    weather: WeatherDTO | None,
    occasion: str,
    note: str,
    intent: IntentDTO | None,
    profile: StyleProfileDTO,
    summary: str | None,
    recent_feedback: list[FeedbackDTO],
    recently_worn: list,
    lang: str,
    *,
    today: date,
    southern_hemisphere: bool = False,
    limits: ContextLimits = DEFAULT_LIMITS,
) -> SuggestContext:
    if intent is not None and intent.occasion:
        occasion = intent.occasion
    season = season_of(today, southern_hemisphere)
    kept, relaxed = prefilter(items, occasion, weather, season, limits, intent)
    index = {i: item.id for i, item in enumerate(kept)}
    position = {item_id: i for i, item_id in index.items()}

    note = mask_pii(note.strip()[: limits.note_chars])
    lines = [f"OCCASION: {occasion}" + (f" — user note: {note}" if note else ""), weather_line(weather, season)]
    if req := request_line(intent, REQUEST_RULE in relaxed):
        lines.append(req)
    lines += style_lines(profile)
    if summary:
        lines.append(f"TASTE SUMMARY: {summary}")
    if fb := feedback_line(recent_feedback, limits.recent_feedback):
        lines.append(fb)
    worn = sorted({position[i] for i in recently_worn if i in position})
    if worn:
        lines.append(f"RECENTLY WORN (last 7 days, prefer variety): {worn}")
    lines.append("WARDROBE (id: category/type | attributes):")
    lines += [item_line(i, item) for i, item in enumerate(kept)]

    text = "\n".join(lines)
    return SuggestContext(
        text=text, items=tuple(kept), index_to_item_id=index,
        items_dropped_count=len(items) - len(kept), relaxed=relaxed, season=season,
        estimated_tokens=len(text) // 4,
    )


def build_capsule_context(capsule, lang: str) -> CapsuleContext:
    """What the model sees when explaining a deterministic capsule (ai.analysis.Capsule): the pieces under
    their numbers, the occasions and season, the outfit count and the gaps. No user text, no ids."""
    items = list(capsule.items)
    lines = [
        f"CAPSULE for {', '.join(capsule.occasions)} ({capsule.season}): {len(items)} pieces, "
        f"{capsule.outfits_possible} wearable outfits",
    ]
    if capsule.gaps:
        wanted = [g.category for g in capsule.gaps if g.category and g.code != "orphan_items"]
        if wanted:
            lines.append("MISSING (would add the most outfits): " + ", ".join(dict.fromkeys(wanted)))
    lines.append("PIECES (id: category/type | attributes):")
    lines += [item_line(i, item) for i, item in enumerate(items)]
    if capsule.sample_outfits:
        position = {item.id: i for i, item in enumerate(items)}
        combos = [" + ".join(str(position[x]) for x in o if x in position) for o in capsule.sample_outfits[:6]]
        lines.append("EXAMPLE OUTFITS (by id): " + "; ".join(combos))
    text = "\n".join(lines)
    return CapsuleContext(text=text, item_ids=tuple(i.id for i in items), estimated_tokens=len(text) // 4)
