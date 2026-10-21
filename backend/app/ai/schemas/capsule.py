"""Model output for a capsule explanation: short text only. The capsule itself (which pieces, how many
outfits, what is missing) is computed deterministically in ai.analysis; the model only explains it."""

from pydantic import BaseModel, model_validator

SUMMARY_CHARS = 500
TIP_CHARS = 180
MAX_TIPS = 5


class CapsuleExplainOut(BaseModel):
    summary: str  # 2-3 sentences: what this capsule is good at
    tips: list[str]  # how to combine the pieces; one line each

    @model_validator(mode="before")
    @classmethod
    def clean(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError("expected a JSON object")
        tips = raw.get("tips") if isinstance(raw.get("tips"), list) else []
        tips = [" ".join(str(t).split())[:TIP_CHARS] for t in tips if str(t).strip()][:MAX_TIPS]
        summary = " ".join(str(raw.get("summary") or "").split())[:SUMMARY_CHARS]
        if not summary:
            raise ValueError("empty summary")
        return {"summary": summary, "tips": tips}

    @classmethod
    def tool_schema(cls) -> dict:
        props = {"summary": {"type": "string"}, "tips": {"type": "array", "items": {"type": "string"}}}
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
