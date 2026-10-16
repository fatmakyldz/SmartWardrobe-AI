"""Fixed vocabularies. Stored values are English keys; the app translates them."""

CATEGORIES = ["top", "bottom", "dress", "outerwear", "shoes", "accessory", "bag"]

COLORS = [
    "black", "white", "grey", "navy", "blue", "lightblue", "green", "olive", "beige", "cream",
    "brown", "khaki", "red", "burgundy", "pink", "purple", "yellow", "orange", "gold", "silver", "multi",
]

PATTERNS = ["solid", "striped", "checked", "floral", "printed", "denim", "knit", "leather", "other"]

SEASONS = ["spring", "summer", "autumn", "winter"]

OCCASIONS = ["casual", "work", "formal", "date", "sport", "party", "travel"]

LANGS = ["en", "tr"]


def clamp_int(value, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def keep_known(values, allowed: list[str], limit: int) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for v in values:
        v = str(v).strip().lower().replace(" ", "")
        if v in allowed and v not in out:
            out.append(v)
    return out[:limit]


def one_of(value, allowed: list[str], default: str) -> str:
    v = str(value or "").strip().lower()
    return v if v in allowed else default
