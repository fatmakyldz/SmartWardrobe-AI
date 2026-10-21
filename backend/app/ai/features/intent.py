"""Natural language → structured outfit request: prompt intent/v1 + IntentOut.

The parsed intent feeds ai.context (occasion, hard avoid-filters, a CONSTRAINTS line); the raw text never
reaches the suggest prompt. PII is masked before the request leaves the server.
"""

import uuid

from ...vocab import CATEGORIES, COLORS, LANG_NAME, OCCASIONS, PATTERNS
from ..context import mask_pii
from ..gateway import AIRequest, AIResponse, BudgetGate, complete
from ..providers import TextPart
from ..schemas.context import IntentDTO
from ..schemas.intent import IntentOut

PROMPT_VERSION = "v1"
REQUEST_CHARS = 200


def to_dto(out: IntentOut) -> IntentDTO:
    return IntentDTO(
        occasion=out.occasion,
        include_categories=tuple(out.include_categories),
        include_colors=tuple(out.include_colors),
        avoid_categories=tuple(out.avoid_categories),
        avoid_colors=tuple(out.avoid_colors),
        avoid_patterns=tuple(out.avoid_patterns),
        wants_outerwear=out.wants_outerwear,
        brief=out.brief,
    )


def parse_request(
    text: str,
    lang: str,
    *,
    subject_id: uuid.UUID,
    tier: str,
    budget: BudgetGate,
    idempotency_key: str | None = None,
) -> tuple[IntentOut, AIResponse]:
    cleaned = mask_pii(" ".join(text.split())[:REQUEST_CHARS])
    resp = complete(
        AIRequest(
            feature="intent",
            subject_id=subject_id,
            tier=tier,
            prompt_version=PROMPT_VERSION,
            system_vars={"language": LANG_NAME[lang], "occasions": OCCASIONS, "categories": CATEGORIES,
                         "colors": COLORS, "patterns": PATTERNS},
            user_content=[TextPart(f"Request: {cleaned}")],
            schema=IntentOut,
            max_output_tokens=300,
            timeout_s=15,
            temperature=0.0,
            idempotency_key=idempotency_key,
        ),
        budget=budget,
    )
    return resp.data, resp
