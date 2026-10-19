"""Tag a clothing photo: prompt tagging/v1 + TaggingOut."""

import uuid

from ...vocab import CATEGORIES, COLORS, PATTERNS, SEASONS
from ..gateway import AIRequest, AIResponse, BudgetGate, complete
from ..providers import ImagePart, TextPart
from ..schemas import TaggingOut

LANG_NAME = {"en": "English", "tr": "Turkish"}
PROMPT_VERSION = "v1"


def tag_image(
    image_jpeg: bytes,
    lang: str,
    *,
    subject_id: uuid.UUID,
    tier: str,
    budget: BudgetGate,
    idempotency_key: str | None = None,
) -> tuple[TaggingOut, AIResponse]:
    resp = complete(
        AIRequest(
            feature="tagging",
            subject_id=subject_id,
            tier=tier,
            prompt_version=PROMPT_VERSION,
            system_vars={"categories": CATEGORIES, "colors": COLORS, "patterns": PATTERNS, "seasons": SEASONS,
                         "language": LANG_NAME[lang]},
            user_content=[TextPart("Catalogue this item."), ImagePart(image_jpeg, "image/jpeg")],
            schema=TaggingOut,
            max_output_tokens=400,
            timeout_s=30,
            temperature=0.1,
            idempotency_key=idempotency_key,
        ),
        budget=budget,
    )
    return resp.data, resp
