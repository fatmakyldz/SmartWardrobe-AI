"""Prompts and validation for the two AI features: tagging a photo and suggesting outfits."""

from .config import get_settings
from .llm import LLMError, chat_json
from .models import Item, Outfit
from .vocab import CATEGORIES, COLORS, OCCASIONS, PATTERNS, SEASONS, clamp_int, keep_known, one_of
from .weather import describe

LANG_NAME = {"en": "English", "tr": "Turkish"}


# ── 1. Tag a clothing photo ─────────────────────────────────────────────

def tag_image(image_data_url: str, lang: str) -> dict:
    s = get_settings()
    system = (
        "You catalogue clothing for a wardrobe app. Look at the photo and describe the single main "
        "garment or accessory. Reply with ONE JSON object and nothing else:\n"
        "{\n"
        f'  "is_clothing": true|false,\n'
        f'  "category": one of {CATEGORIES},\n'
        '  "subcategory": short English noun, e.g. "t-shirt", "jeans", "sneakers", "blazer",\n'
        f'  "name": a short friendly name in {LANG_NAME[lang]} (max 5 words), e.g. a colour + item,\n'
        f'  "colors": 1-3 values from {COLORS}, dominant first,\n'
        f'  "pattern": one of {PATTERNS},\n'
        '  "warmth": 1-5 (1 = very light summer piece, 5 = heavy winter piece),\n'
        '  "formality": 1-5 (1 = sport/lounge, 3 = smart casual, 5 = black tie),\n'
        f'  "seasons": values from {SEASONS} it suits\n'
        "}\n"
        'If the photo shows no clothing, set "is_clothing": false and fill the rest with your best guess.'
    )
    raw = chat_json(
        [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Catalogue this item."},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ],
        model=s.groq_vision_model,
        temperature=0.1,
        max_tokens=400,
    )
    return clean_tags(raw)


def clean_tags(raw: dict) -> dict:
    """Never trust model output: coerce everything into the fixed vocabularies."""
    seasons = keep_known(raw.get("seasons"), SEASONS, 4)
    return {
        "is_clothing": bool(raw.get("is_clothing", True)),
        "category": one_of(raw.get("category"), CATEGORIES, "top"),
        "subcategory": str(raw.get("subcategory") or "")[:60],
        "name": str(raw.get("name") or "")[:120],
        "colors": keep_known(raw.get("colors"), COLORS, 3),
        "pattern": one_of(raw.get("pattern"), PATTERNS, "solid"),
        "warmth": clamp_int(raw.get("warmth"), 1, 5, 3),
        "formality": clamp_int(raw.get("formality"), 1, 5, 2),
        "seasons": seasons or list(SEASONS),
    }


# ── 2. Suggest outfits from the user's own wardrobe ──────────────────────

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


def suggest(
    items: list[Item],
    weather: dict | None,
    occasion: str,
    note: str,
    lang: str,
    history: list[Outfit],
    count: int = 3,
) -> list[dict]:
    s = get_settings()
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

    system = (
        "You are a thoughtful personal stylist. Build outfits ONLY from the numbered wardrobe items. "
        "Every outfit needs either (a top + a bottom) or a dress, plus shoes if any exist; add outerwear "
        "when it is cold, windy or rainy, and accessories/bags when they genuinely help. Never use two items "
        "of the same category except accessories. Match warmth to the weather and formality to the occasion, "
        "keep colours harmonious, and make the outfits clearly different from each other.\n"
        f"Write titles and reasons in {LANG_NAME[lang]}. Reasons: 1-2 short, warm sentences mentioning "
        "the weather or occasion.\n"
        'Reply with ONE JSON object: {"outfits": [{"title": str (max 6 words), "items": [ids], "reason": str}]} '
        f"with up to {count} outfits."
    )
    raw = chat_json(
        [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(lines)}],
        model=s.groq_text_model,
        temperature=0.7,
        max_tokens=1800,
    )
    outfits = validate_outfits(raw, index)
    if not outfits:
        raise LLMError("ai_bad_reply")
    return outfits[:count]


def validate_outfits(raw: dict, index: dict[int, Item]) -> list[dict]:
    result, seen = [], set()
    for o in raw.get("outfits") or []:
        if not isinstance(o, dict):
            continue
        chosen: list[Item] = []
        used_categories: set[str] = set()
        for x in o.get("items") or []:
            try:
                item = index[int(x)]
            except (KeyError, ValueError, TypeError):
                continue  # hallucinated id
            if item in chosen:
                continue
            if item.category in used_categories and item.category != "accessory":
                continue
            chosen.append(item)
            used_categories.add(item.category)

        cats = {i.category for i in chosen}
        complete = "dress" in cats or {"top", "bottom"} <= cats
        signature = frozenset(i.id for i in chosen)
        if not complete or signature in seen:
            continue
        seen.add(signature)
        result.append(
            {
                "title": str(o.get("title") or "")[:120],
                "reason": str(o.get("reason") or "")[:600],
                "items": chosen,
            }
        )
    return result


def wardrobe_ready(items: list[Item]) -> bool:
    cats = {i.category for i in items}
    return "dress" in cats or {"top", "bottom"} <= cats


__all__ = ["tag_image", "clean_tags", "suggest", "validate_outfits", "wardrobe_ready", "OCCASIONS"]
