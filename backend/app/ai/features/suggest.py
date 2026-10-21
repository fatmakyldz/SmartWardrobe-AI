"""Suggest outfits from the user's own wardrobe: prompt suggest/v2 + SuggestOut + id/category checks.

The context (which items, in which order, under which numbers) comes from ai.context; this module only
asks the model and keeps the answers that respect the wardrobe.
"""

import uuid
from dataclasses import dataclass

from ...outfit_rules import complete_outfit
from ...vocab import LANG_NAME
from ..gateway import AIRequest, AIResponse, BudgetGate, complete
from ..providers import TextPart
from ..schemas import SuggestOut
from ..schemas.context import ItemDTO, SuggestContext

PROMPT_VERSION = "v2"  # v1 system text, §6 context


@dataclass(frozen=True)
class ValidatedOutfit:
    title: str
    reason: str
    items: tuple[ItemDTO, ...]


def wardrobe_ready(items) -> bool:
    return complete_outfit([i.category for i in items])


def validate_outfits(out: SuggestOut, ctx: SuggestContext) -> list[ValidatedOutfit]:
    """Keep only outfits built from numbers in ctx.index_to_item_id, one item per category (accessories
    aside), complete (top + bottom, or a dress) and not repeated."""
    by_index = dict(enumerate(ctx.items))
    result, seen = [], set()
    for o in out.outfits:
        chosen: list[ItemDTO] = []
        used: set[str] = set()
        for x in o.items:
            if x not in ctx.index_to_item_id:
                continue  # hallucinated id
            item = by_index[x]
            if item in chosen or (item.category in used and item.category != "accessory"):
                continue
            chosen.append(item)
            used.add(item.category)
        signature = frozenset(i.id for i in chosen)
        if not complete_outfit([i.category for i in chosen]) or signature in seen:
            continue
        seen.add(signature)
        result.append(ValidatedOutfit(title=o.title, reason=o.reason, items=tuple(chosen)))
    return result


def suggest(
    ctx: SuggestContext,
    lang: str,
    *,
    subject_id: uuid.UUID,
    tier: str,
    budget: BudgetGate,
    count: int = 3,
    idempotency_key: str | None = None,
) -> tuple[list[ValidatedOutfit], AIResponse]:
    def check(out: SuggestOut) -> None:
        if not validate_outfits(out, ctx):
            raise ValueError("no valid outfit")

    resp = complete(
        AIRequest(
            feature="suggest",
            subject_id=subject_id,
            tier=tier,
            prompt_version=PROMPT_VERSION,
            system_vars={"language": LANG_NAME[lang], "count": count},
            user_content=[TextPart(ctx.text)],
            schema=SuggestOut,
            max_output_tokens=1800,
            timeout_s=45,
            temperature=0.7,
            idempotency_key=idempotency_key,
            check=check,
        ),
        budget=budget,
    )
    return validate_outfits(resp.data, ctx)[:count], resp
