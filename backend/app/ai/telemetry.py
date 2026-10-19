"""The gateway's only DB writes: ai_requests (one per logical request) and ai_request_attempts (one per
provider call). Its own short session, so the gateway never needs the caller's. Plus one JSON log line
per attempt — never prompt text or user content, only the prompt hash and token counts."""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import AIRequest as AIRequestRow
from ..models import AIRequestAttempt

log = logging.getLogger("ai")


@dataclass
class AttemptRecord:
    attempt_no: int
    provider: str
    model: str
    model_class: str
    status: str  # ok / timeout / rate_limited / bad_output / error
    error_code: str | None = None
    detail: str | None = None  # provider's error message, ≤200 chars; logged, not stored
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd_micro: int = 0
    latency_ms: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RequestRecord:
    id: uuid.UUID
    subject_id: uuid.UUID
    feature: str
    prompt_version: str
    prompt_hash: str
    status: str  # ok / fallback / error / budget
    attempts: list[AttemptRecord]
    final: AttemptRecord | None = None
    estimated_input_tokens: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def log_attempt(request_id: uuid.UUID, feature: str, prompt_hash: str, a: AttemptRecord) -> None:
    log.info(json.dumps({
        "event": "ai_attempt",
        "ai_request_id": str(request_id),
        "feature": feature,
        "provider": a.provider,
        "model": a.model,
        "status": a.status,
        "error_code": a.error_code,
        "detail": a.detail,
        "latency_ms": a.latency_ms,
        "attempt": a.attempt_no,
        "input_tokens": a.input_tokens,
        "output_tokens": a.output_tokens,
        "prompt_hash": prompt_hash[:16],
    }))


class Telemetry:
    def __init__(self, session_factory=None):
        if session_factory is None:
            from ..db import SessionLocal

            session_factory = SessionLocal
        self._session_factory = session_factory

    def record(self, r: RequestRecord) -> bool:
        final = r.final
        row = AIRequestRow(
            id=r.id,
            subject_id=r.subject_id,
            feature=r.feature,
            prompt_version=r.prompt_version,
            status=r.status,
            final_provider=final.provider if final else None,
            final_model=final.model if final else None,
            final_model_class=final.model_class if final else None,
            input_tokens_total=sum(a.input_tokens for a in r.attempts),
            output_tokens_total=sum(a.output_tokens for a in r.attempts),
            cost_usd_micro_total=sum(a.cost_usd_micro for a in r.attempts),
            latency_ms_total=sum(a.latency_ms for a in r.attempts),
            attempts_count=len(r.attempts),
            fallback_used=r.status == "fallback",
            prompt_hash=r.prompt_hash,
            estimated_input_tokens=r.estimated_input_tokens,
            created_at=r.created_at,
        )
        row.attempts = [
            AIRequestAttempt(
                attempt_no=a.attempt_no, provider=a.provider, model=a.model, status=a.status,
                error_code=a.error_code, input_tokens=a.input_tokens, output_tokens=a.output_tokens,
                cost_usd_micro=a.cost_usd_micro, latency_ms=a.latency_ms, created_at=a.created_at,
            )
            for a in r.attempts
        ]
        db: Session = self._session_factory()
        try:
            db.add(row)
            db.commit()
            return True
        except Exception:  # telemetry must never break the user's request
            db.rollback()
            log.exception("could not write ai_requests row %s", r.id)
            return False
        finally:
            db.close()
