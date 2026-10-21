"""Capsule wardrobe (AI-06): the capsule is chosen deterministically (ai.analysis.build_capsule); this
module asks the model to explain it — prompt capsule_explain/v1 + CapsuleExplainOut. Premium tier routes
capsule_explain to the mid model (routes.default.json); the pieces and numbers never change."""

import uuid

from ...vocab import LANG_NAME
from ...vocab import LANG_NAME
from ..gateway import AIRequest, AIResponse, BudgetGate, complete
from ..providers import TextPart
from ..schemas.capsule import MAX_TIPS, CapsuleExplainOut
from ..schemas.context import CapsuleContext

PROMPT_VERSION = "v1"


def explain(
    ctx: CapsuleContext,
    lang: str,
    *,
    subject_id: uuid.UUID,
    tier: str,
    budget: BudgetGate,
    idempotency_key: str | None = None,
) -> tuple[CapsuleExplainOut, AIResponse]:
    resp = complete(
        AIRequest(
            feature="capsule_explain",
            subject_id=subject_id,
            tier=tier,
            prompt_version=PROMPT_VERSION,
            system_vars={"language": LANG_NAME[lang], "max_tips": MAX_TIPS},
            user_content=[TextPart(ctx.text)],
            schema=CapsuleExplainOut,
            max_output_tokens=700,
            timeout_s=30,
            temperature=0.5,
            idempotency_key=idempotency_key,
        ),
        budget=budget,
    )
    return resp.data, resp
