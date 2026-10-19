"""Model output for outfit suggestions: item numbers only. Which numbers are valid is checked in features.suggest."""

from pydantic import BaseModel, model_validator


class OutfitDraft(BaseModel):
    title: str
    items: list[int]
    reason: str


class SuggestOut(BaseModel):
    outfits: list[OutfitDraft]

    @model_validator(mode="before")
    @classmethod
    def clean(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError("expected a JSON object")
        outfits = []
        for o in raw.get("outfits") or []:
            if not isinstance(o, dict):
                continue
            items = []
            for x in o.get("items") or []:
                try:
                    items.append(int(x))
                except (ValueError, TypeError):
                    continue  # hallucinated id
            # Models sometimes end a field with a newline; strip before storing.
            outfits.append({"title": str(o.get("title") or "").strip()[:120], "items": items,
                            "reason": str(o.get("reason") or "").strip()[:600]})
        return {"outfits": outfits}

    @classmethod
    def tool_schema(cls) -> dict:
        outfit = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "items": {"type": "array", "items": {"type": "integer"}},
                "reason": {"type": "string"},
            },
            "required": ["title", "items", "reason"],
            "additionalProperties": False,
        }
        return {
            "type": "object",
            "properties": {"outfits": {"type": "array", "items": outfit}},
            "required": ["outfits"],
            "additionalProperties": False,
        }
