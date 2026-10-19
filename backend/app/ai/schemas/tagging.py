"""Model output for tagging a photo. Values are coerced into the fixed vocabularies, never trusted."""

from pydantic import BaseModel, model_validator

from ...vocab import CATEGORIES, COLORS, PATTERNS, SEASONS, clamp_int, keep_known, one_of


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
        }
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
