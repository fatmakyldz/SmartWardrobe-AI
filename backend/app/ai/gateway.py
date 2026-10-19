"""The single way into an LLM: budget → model chain → attempts / fallback → schema check → telemetry.

The gateway knows a pseudonymous subject id, never a user object, e-mail or DB session. It asks the
budget gate (entitlements) before calling out and reports every attempt's tokens back to it.
"""

import logging
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ValidationError

from ..config import get_settings
from . import routing
from .errors import AIError
from .prompts import registry
from .providers import PROVIDERS, ImagePart, Part, ProviderCall, ProviderError, TextPart
from .telemetry import AttemptRecord, RequestRecord, Telemetry, log_attempt

log = logging.getLogger("ai")

IDEMPOTENCY_TTL_S = 60
BACKOFF_S = (0.5, 1.5)
REPAIR_NOTE = (
    "Your previous answer did not match the required format. Answer again with exactly one JSON "
    "object that follows the instructions; use only the item numbers listed."
)
IMAGE_TOKENS_ESTIMATE = 1600
# chars/4 undercounts what providers bill: measured on the live suggest route, real input was ~2.5x the
# text estimate, plus a fixed part for the tool schema and instructions. Only the pre-call budget check
# uses this; consume() always records the real tokens. scripts/ai_report.py shows the real/estimate ratio.
TEXT_TOKEN_FACTOR = 2.5
FIXED_INPUT_TOKENS = 600


class BudgetDecisionLike(Protocol):
    allowed: bool
    remaining_requests: int | None
    remaining_tokens: int
    reset_at: str


class BudgetGate(Protocol):
    def check(self, feature: str, estimated_tokens: int) -> BudgetDecisionLike: ...

    def consume(self, feature: str, tokens: int, succeeded: bool = False) -> None: ...


@dataclass(frozen=True)
class AIRequest:
    feature: str  # "tagging" | "suggest" | …
    subject_id: uuid.UUID  # pseudonymous; only used to key budgets and telemetry
    tier: str  # entitlements.model_tier
    prompt_version: str
    system_vars: dict
    user_content: list[Part]
    schema: type[BaseModel]  # must provide tool_schema()
    max_output_tokens: int
    timeout_s: float = 30
    idempotency_key: str | None = None
    temperature: float | None = None
    check: Callable[[BaseModel], None] | None = None  # extra validation; raise ValueError → bad_output


@dataclass(frozen=True)
class AIResponse:
    data: BaseModel
    provider: str
    model: str
    model_class: str
    input_tokens: int
    output_tokens: int
    cost_usd_micro: int
    latency_ms: int
    attempts: int
    fallback_used: bool
    request_id: uuid.UUID | None
    prompt_version: str


class _Idempotency:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, AIResponse]] = {}

    def get(self, key: str) -> AIResponse | None:
        with self._lock:
            hit = self._entries.get(key)
            return hit[1] if hit and hit[0] > time.monotonic() else None

    def put(self, key: str, response: AIResponse) -> None:
        now = time.monotonic()
        with self._lock:
            self._entries = {k: v for k, v in self._entries.items() if v[0] > now}
            self._entries[key] = (now + IDEMPOTENCY_TTL_S, response)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


IDEMPOTENCY = _Idempotency()
sleep = time.sleep  # tests patch this


def estimate_input_tokens(system: str, parts: list[Part]) -> int:
    chars = len(system) + sum(len(p.text) for p in parts if isinstance(p, TextPart))
    images = sum(1 for p in parts if isinstance(p, ImagePart))
    return round(chars / 4 * TEXT_TOKEN_FACTOR) + FIXED_INPUT_TOKENS + images * IMAGE_TOKENS_ESTIMATE


def _final_error(kinds: list[str]) -> AIError:
    # Models skipped for auth / config errors say nothing about load; judge by the models that ran.
    ran = [k for k in kinds if k not in ("auth", "config")]
    if ran and all(k in ("timeout", "rate_limited") for k in ran):
        return AIError("ai_busy")
    if ran and all(k == "bad_output" for k in ran):
        return AIError("ai_bad_reply")
    return AIError("ai_unavailable")


def complete(req: AIRequest, *, budget: BudgetGate, telemetry: Telemetry | None = None) -> AIResponse:
    telemetry = telemetry or Telemetry()
    cache_key = f"{req.subject_id}:{req.feature}:{req.idempotency_key}" if req.idempotency_key else None
    if cache_key and (cached := IDEMPOTENCY.get(cache_key)):
        return cached

    template = registry.get(req.feature, req.prompt_version)
    system = template.render(req.system_vars)
    phash = registry.prompt_hash(system)
    if get_settings().ai_debug_log:  # local only; refused at startup with Postgres
        texts = "\n".join(p.text for p in req.user_content if isinstance(p, TextPart))
        print(f"[ai debug] {req.feature}/{req.prompt_version}\n--- system ---\n{system}\n--- user ---\n{texts}",
              file=sys.stderr)

    request_id = uuid.uuid4()

    def record(status: str, attempts: list[AttemptRecord], final: AttemptRecord | None = None) -> bool:
        return telemetry.record(RequestRecord(id=request_id, subject_id=req.subject_id, feature=req.feature,
                                       prompt_version=req.prompt_version, prompt_hash=phash, status=status,
                                       attempts=attempts, final=final, estimated_input_tokens=estimated_input))

    estimated_input = estimate_input_tokens(system, req.user_content)
    decision = budget.check(req.feature, estimated_input + req.max_output_tokens)
    if not decision.allowed:
        record("budget", [])
        raise AIError("budget_exceeded", reset_at=decision.reset_at,
                      remaining={"requests": decision.remaining_requests, "tokens": decision.remaining_tokens})

    candidates = [c for c in routing.chain(req.feature, req.tier) if PROVIDERS[c.provider].configured()]
    if not candidates:
        record("error", [])
        raise AIError("ai_not_configured")

    timeout = routing.timeout_for(req.feature, req.timeout_s)
    max_tries = max(1, routing.attempts_per_candidate())
    json_schema = req.schema.tool_schema()
    attempts: list[AttemptRecord] = []
    failures: list[str] = []

    for position, cand in enumerate(candidates):
        provider = PROVIDERS[cand.provider]
        repair: str | None = None
        for try_no in range(1, max_tries + 1):
            call = ProviderCall(system=system, parts=req.user_content, schema_name=req.feature,
                                json_schema=json_schema, max_output_tokens=req.max_output_tokens,
                                timeout_s=timeout, temperature=req.temperature, options=cand.options,
                                repair_note=repair)
            started = time.monotonic()
            tokens = (0, 0, 0, 0)  # input, output, cache read, cache write
            data = None
            kind, error_code, detail = "ok", None, None
            try:
                result = provider.complete_json(call, cand.model)
                tokens = (result.input_tokens, result.output_tokens, result.cache_read_tokens, result.cache_write_tokens)
                data = req.schema.model_validate(result.data)
                if req.check:
                    req.check(data)
            except ProviderError as e:
                # error_code is the failure kind (auth / config / unavailable / …); for a plain "error",
                # the short provider reason (e.g. "refusal").
                kind = e.kind
                error_code = (e.message[:60] or "error") if e.kind == "error" else e.kind
                detail = e.message or None
                tokens = (e.input_tokens, e.output_tokens, e.cache_read_tokens, e.cache_write_tokens)
            except (ValidationError, ValueError) as e:
                kind, error_code = "bad_output", type(e).__name__
                # A ValidationError's text quotes the model's output, which is never logged.
                detail = f"{e.error_count()} schema errors" if isinstance(e, ValidationError) else str(e)[:200]
            except Exception as e:  # a provider bug must not take the request down with an unlogged 500
                log.exception("provider %s crashed", cand.provider)
                kind, error_code = "error", type(e).__name__

            inp, out, cache_read, cache_write = tokens
            attempt = AttemptRecord(
                attempt_no=len(attempts) + 1, provider=cand.provider, model=cand.model, model_class=cand.model_class,
                status="ok" if kind == "ok" else ("error" if kind in ("auth", "config", "unavailable") else kind),
                error_code=None if kind == "ok" else error_code, detail=detail,
                input_tokens=inp + cache_read + cache_write, output_tokens=out,
                cost_usd_micro=cand.cost_usd_micro(inp, out, cache_read, cache_write),
                latency_ms=int((time.monotonic() - started) * 1000),
            )
            attempts.append(attempt)
            log_attempt(request_id, req.feature, phash, attempt)
            billed = attempt.input_tokens + attempt.output_tokens
            routing.HEALTH.add_tokens(cand.model_class, billed)
            # Every billed attempt counts against the token budget; the request counter only on success.
            budget.consume(req.feature, billed, succeeded=kind == "ok")

            if kind == "ok":
                routing.HEALTH.success(cand.provider)
                status = "fallback" if position > 0 else "ok"
                recorded = record(status, attempts, attempt)
                response = AIResponse(
                    data=data, provider=cand.provider, model=cand.model, model_class=cand.model_class,
                    input_tokens=sum(a.input_tokens for a in attempts),
                    output_tokens=sum(a.output_tokens for a in attempts),
                    cost_usd_micro=sum(a.cost_usd_micro for a in attempts),
                    latency_ms=sum(a.latency_ms for a in attempts), attempts=len(attempts),
                    fallback_used=position > 0, prompt_version=req.prompt_version,
                    # None if the telemetry row could not be written, so callers don't point an FK at nothing.
                    request_id=request_id if recorded else None,
                )
                if cache_key:
                    IDEMPOTENCY.put(cache_key, response)
                return response

            failures.append(kind)
            if kind in ("timeout", "unavailable"):
                routing.HEALTH.failure(cand.provider)
            if try_no < max_tries and kind in ("timeout", "rate_limited"):
                sleep(BACKOFF_S[min(try_no - 1, len(BACKOFF_S) - 1)])
                continue
            if try_no < max_tries and kind == "bad_output":
                repair = REPAIR_NOTE
                continue
            break  # auth / config / unavailable / error, or retries used up → next candidate

    record("error", attempts, attempts[-1] if attempts else None)
    raise _final_error(failures)
