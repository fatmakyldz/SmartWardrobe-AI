"""Suggest outfits from the user's own wardrobe: prompt suggest/v1 + SuggestOut + id/category checks."""

import uuid

from ...models import Item, Outfit
from ...weather import describe
from ..gateway import AIRequest, AIResponse, BudgetGate, complete
from ..providers import TextPart
from ..schemas import SuggestOut

LANG_NAME = {"en": "English", "tr": "Turkish"}
PROMPT_VERSION = "v1"


def _item_line(i: int, item: Item) -> str:
    return (
        f"{i}: {item.category}/{item.subcategory or '-'} | colors={','.join(item.colors) or '-'} "
        f"| pattern={item.pattern} | warmth={item.warmth} | formality={item.formality} "
        f"| seasons={','.join(item.seasons) or '-'}"
    )


def _weather_line(w: dict) -> str:
    return (
        f"now {w.get('temp')}°C (feels {w.get('feels_like')}°C), today {w.get('min')}–{w.get('max')}°C, "
        f"{describe(w.get('code'))}, rain chance {w.get('rain_chance')}%, wind {w.get('wind_kmh')} km/h"
    )


def wardrobe_ready(items: list[Item]) -> bool:
    cats = {i.category for i in items}
    return "dress" in cats or {"top", "bottom"} <= cats


def validate_outfits(out: SuggestOut, index: dict[int, Item]) -> list[dict]:
    """Keep only outfits built from real item numbers, one item per category (accessories aside),
    complete (top + bottom, or a dress) and not repeated."""
    result, seen = [], set()
    for o in out.outfits:
        chosen: list[Item] = []
        used_categories: set[str] = set()
        for x in o.items:
            item = index.get(x)
            if item is None:
                continue  # hallucinated id
            if item in chosen:
                continue
            if item.category in used_categories and item.category != "accessory":
                continue
            chosen.append(item)
            used_categories.add(item.category)

        cats = {i.category for i in chosen}
        complete_ = "dress" in cats or {"top", "bottom"} <= cats
        signature = frozenset(i.id for i in chosen)
        if not complete_ or signature in seen:
            continue
        seen.add(signature)
        result.append({"title": o.title, "reason": o.reason, "items": chosen})
    return result


def suggest(
    items: list[Item],
    weather: dict | None,
    occasion: str,
    note: str,
    lang: str,
    history: list[Outfit],
    *,
    subject_id: uuid.UUID,
    tier: str,
    budget: BudgetGate,
    count: int = 3,
    idempotency_key: str | None = None,
) -> tuple[list[dict], AIResponse]:
    index = {i: item for i, item in enumerate(items)}
    by_id = {str(item.id): i for i, item in index.items()}

    liked, disliked = [], []
    for o in history:
        idxs = [by_id[x] for x in o.item_ids if x in by_id]
        if len(idxs) >= 2:
            (liked if o.rating > 0 else disliked).append(idxs)

    lines = [
        f"OCCASION: {occasion}" + (f" — user note: {note}" if note else ""),
        f"WEATHER: {_weather_line(weather)}" if weather else "WEATHER: unknown, assume mild indoor day",
        "WARDROBE (id: category/type | attributes):",
        *[_item_line(i, it) for i, it in index.items()],
    ]
    if liked:
        lines.append(f"USER LIKED these combinations before: {liked[:8]}")
    if disliked:
        lines.append(f"USER DISLIKED these combinations: {disliked[:8]} — avoid repeating them")

    def check(out: SuggestOut) -> None:
        if not validate_outfits(out, index):
            raise ValueError("no valid outfit")

    resp = complete(
        AIRequest(
            feature="suggest",
            subject_id=subject_id,
            tier=tier,
            prompt_version=PROMPT_VERSION,
            system_vars={"language": LANG_NAME[lang], "count": count},
            user_content=[TextPart("\n".join(lines))],
            schema=SuggestOut,
            max_output_tokens=1800,
            timeout_s=45,
            temperature=0.7,
            idempotency_key=idempotency_key,
            check=check,
        ),
        budget=budget,
    )
    return validate_outfits(resp.data, index)[:count], resp
