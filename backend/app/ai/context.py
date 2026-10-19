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
    ContextLimits,
    FeedbackDTO,
    IntentDTO,
    ItemDTO,
    StyleProfileDTO,
    SuggestContext,
    WeatherDTO,
)

RELAX_ORDER = ("season", "warmth", "formality")
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


def _passes(item: ItemDTO, rule: str, season: str, feels: float | None, window: tuple[int, int],
            limits: ContextLimits) -> bool:
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
              limits: ContextLimits = DEFAULT_LIMITS) -> tuple[list[ItemDTO], tuple[str, ...]]:
    """§6 step 1. Returns the kept items in final order and the filters that had to be relaxed."""
    active = [i for i in items if not i.archived]
    feels = None
    if weather is not None:
        feels = weather.feels_like if weather.feels_like is not None else weather.temp
    window = OCCASION_FORMALITY.get(occasion, (1, 5))

    rules = list(RELAX_ORDER)
    relaxed: list[str] = []
    while True:
        kept = [i for i in active if all(_passes(i, r, season, feels, window, limits) for r in rules)]
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
    kept, relaxed = prefilter(items, occasion, weather, season, limits)
    index = {i: item.id for i, item in enumerate(kept)}
    position = {item_id: i for i, item_id in index.items()}

    note = mask_pii(note.strip()[: limits.note_chars])
    lines = [f"OCCASION: {occasion}" + (f" — user note: {note}" if note else ""), weather_line(weather, season)]
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
