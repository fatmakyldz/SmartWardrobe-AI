"""Model output for tagging a photo. Values are coerced into the fixed vocabularies, never trusted."""

from pydantic import BaseModel, model_validator

from ...vocab import CATEGORIES, COLORS, PATTERNS, SEASONS, clamp_int, keep_known, one_of


TAG_FIELDS = ["category", "subcategory", "colors", "pattern", "warmth", "formality", "seasons"]


class TaggingOut(BaseModel):
    is_clothing: bool
    category: str
    subcategory: str
    name: str
    colors: list[str]
    pattern: str
    warmth: int
    formality: int
    seasons: list[str]
    confidence: float | None  # 0-1 for the whole description; None when the model didn't say (v1)
    uncertain: list[str]  # TAG_FIELDS the model flagged; the app highlights them for the user to check

    @model_validator(mode="before")
    @classmethod
    def clean(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError("expected a JSON object")
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
            "confidence": _confidence(raw.get("confidence")),
            "uncertain": keep_known(raw.get("uncertain"), TAG_FIELDS, len(TAG_FIELDS)),
        }

    @classmethod
    def tool_schema(cls) -> dict:
        """Strict JSON schema sent to providers that can enforce one."""
        one_to_five = {"type": "integer", "enum": [1, 2, 3, 4, 5]}
        props = {
            "is_clothing": {"type": "boolean"},
            "category": {"type": "string", "enum": CATEGORIES},
            "subcategory": {"type": "string"},
            "name": {"type": "string"},
            "colors": {"type": "array", "items": {"type": "string", "enum": COLORS}},
            "pattern": {"type": "string", "enum": PATTERNS},
            "warmth": one_to_five,
            "formality": one_to_five,
            "seasons": {"type": "array", "items": {"type": "string", "enum": SEASONS}},
            "confidence": {"type": "number"},  # 0-1 by the prompt; clamped in _confidence (strict schemas take no bounds)
            "uncertain": {"type": "array", "items": {"type": "string", "enum": TAG_FIELDS}},
        }
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _confidence(value) -> float | None:
    try:
        return round(max(0.0, min(1.0, float(value))), 2)
    except (TypeError, ValueError):
        return None
