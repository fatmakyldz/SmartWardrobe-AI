import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from app.db import SessionLocal, engine
from app.models import AIRequest, AIRequestAttempt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ai_report  # noqa: E402


def _req(feature, status, cost, latency, attempts, day=datetime(2026, 10, 18, 9, tzinfo=timezone.utc)):
    r = AIRequest(id=uuid.uuid4(), subject_id=uuid.uuid4(), feature=feature, prompt_version="v1", status=status,
                  input_tokens_total=1000, output_tokens_total=100, cost_usd_micro_total=cost,
                  latency_ms_total=latency, attempts_count=len(attempts), fallback_used=status == "fallback",
                  created_at=day)
    r.attempts = [AIRequestAttempt(attempt_no=n + 1, provider=p, model=m, status=s, error_code=None if s == "ok" else s,
                                   created_at=day) for n, (p, m, s) in enumerate(attempts)]
    return r


def test_report_summarises_yesterday():
    with SessionLocal() as db:
        db.add_all([
            _req("tagging", "ok", 150, 800, [("anthropic", "haiku", "ok")]),
            _req("suggest", "fallback", 4000, 5000, [("anthropic", "sonnet", "timeout"), ("groq", "gpt", "ok")]),
            _req("suggest", "budget", 0, 0, []),
            _req("suggest", "ok", 9999, 1, [("anthropic", "sonnet", "ok")], day=datetime(2026, 10, 17, tzinfo=timezone.utc)),
        ])
        db.commit()
    with engine.connect() as conn:
        text = ai_report.report(conn, date(2026, 10, 18))
    assert "requests 3" in text and "cost $0.0042" in text
    assert "fallback 1 (33.3%)" in text and "budget 1 (33.3%)" in text
    assert "anthropic/sonnet: 1 (timeout 1); failure rate 100.0%" in text
    assert "failure codes: timeout 1" in text
    with engine.connect() as conn:
        assert "No AI requests." in ai_report.report(conn, date(2026, 10, 1))
