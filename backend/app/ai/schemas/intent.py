"""Model output for a natural-language outfit request. Everything is coerced into the fixed vocabularies;
free text never reaches the suggest prompt except the short English `brief`."""

from pydantic import BaseModel, model_validator

from ...vocab import CATEGORIES, COLORS, OCCASIONS, PATTERNS, keep_known, one_of

BRIEF_CHARS = 160


class IntentOut(BaseModel):
    occasion: str | None  # one of OCCASIONS, or None when the request doesn't say
    include_categories: list[str]
    include_colors: list[str]
    avoid_categories: list[str]
    avoid_colors: list[str]
    avoid_patterns: list[str]
    wants_outerwear: bool | None
    brief: str  # what the user asked for, in one short English sentence (shown to the stylist model)

    @model_validator(mode="before")
    @classmethod
    def clean(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError("expected a JSON object")
        occasion = one_of(raw.get("occasion"), OCCASIONS, "")
        include_cats = keep_known(raw.get("include_categories"), CATEGORIES, 4)
        avoid_cats = [c for c in keep_known(raw.get("avoid_categories"), CATEGORIES, 4) if c not in include_cats]
        include_cols = keep_known(raw.get("include_colors"), COLORS, 4)
        avoid_cols = [c for c in keep_known(raw.get("avoid_colors"), COLORS, 4) if c not in include_cols]
        wants = raw.get("wants_outerwear")
        return {
            "occasion": occasion or None,
            "include_categories": include_cats,
            "include_colors": include_cols,
            "avoid_categories": avoid_cats,
            "avoid_colors": avoid_cols,
            "avoid_patterns": keep_known(raw.get("avoid_patterns"), PATTERNS, 4),
            "wants_outerwear": wants if isinstance(wants, bool) else None,
            "brief": " ".join(str(raw.get("brief") or "").split())[:BRIEF_CHARS],
        }

    @property
    def is_empty(self) -> bool:
        return not any([self.occasion, self.include_categories, self.include_colors, self.avoid_categories,
                        self.avoid_colors, self.avoid_patterns, self.wants_outerwear is not None, self.brief])

    @classmethod
    def tool_schema(cls) -> dict:
        def arr(values: list[str]) -> dict:
            return {"type": "array", "items": {"type": "string", "enum": values}}

        props = {
            "occasion": {"type": ["string", "null"], "enum": [*OCCASIONS, None]},
            "include_categories": arr(CATEGORIES),
            "include_colors": arr(COLORS),
            "avoid_categories": arr(CATEGORIES),
            "avoid_colors": arr(COLORS),
            "avoid_patterns": arr(PATTERNS),
            "wants_outerwear": {"type": ["boolean", "null"]},
            "brief": {"type": "string"},
        }
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
