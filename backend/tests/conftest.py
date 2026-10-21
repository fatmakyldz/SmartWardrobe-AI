import json
import os
import tempfile

# SQLite by default. CI also runs the suite on Postgres via TEST_DATABASE_URL — a separate
# variable so a DATABASE_URL exported for real work is never dropped by these tests.
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
else:
    _db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"
os.environ["GROQ_API_KEY"] = "test-key"
os.environ["ANTHROPIC_API_KEY"] = ""
# Every model in the chain is the fake provider: two candidates per feature, so fallback is testable.
os.environ["AI_ROUTES"] = json.dumps({
    "models": {
        "vision-a": {"provider": "fake", "model": "fake-vision-a", "in_usd_per_mtok": 1.0, "out_usd_per_mtok": 5.0},
        "vision-b": {"provider": "fake", "model": "fake-vision-b", "in_usd_per_mtok": 0.5, "out_usd_per_mtok": 1.0},
        "text-a": {"provider": "fake", "model": "fake-text-a", "in_usd_per_mtok": 2.0, "out_usd_per_mtok": 10.0},
        "text-b": {"provider": "fake", "model": "fake-text-b", "in_usd_per_mtok": 0.1, "out_usd_per_mtok": 0.5},
    },
    "routes": {
        "tagging": {"standard": ["vision-a", "vision-b"], "premium": ["vision-a", "vision-b"]},
        "suggest": {"standard": ["text-a", "text-b"], "premium": ["text-a", "text-b"]},
        "intent": {"standard": ["vision-a", "text-b"], "premium": ["vision-a", "text-b"]},
        # like production: premium explanations go to the mid (text-a) model, standard to the small one
        "capsule_explain": {"standard": ["vision-a", "text-b"], "premium": ["text-a", "text-b"]},
    },
    "attempts_per_candidate": 2,
})
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-32b"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"
os.environ["CORS_ORIGINS"] = "https://wardrobe.fomertech.com"  # required with Postgres (CI runs both)
os.environ["RESEND_API_KEY"] = ""  # the fake email backend: messages land in services.email.OUTBOX

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import limiter  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    limiter.reset()
    yield


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch):
    """The fake provider behind every route. Script answers with fake_ai.script(model, ...) or fake_ai.respond."""
    from app.ai import gateway, routing
    from app.ai.providers import FAKE

    FAKE.reset()
    gateway.IDEMPOTENCY.clear()
    routing.HEALTH.reset()
    monkeypatch.setattr(gateway, "sleep", lambda s: None)
    return FAKE


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def outbox():
    from app.services import email

    email.OUTBOX.clear()
    return email.OUTBOX


def verify_email(email: str) -> None:
    from datetime import datetime, timezone

    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        db.query(User).filter(User.email == email).one().email_verified_at = datetime.now(timezone.utc)
        db.commit()


@pytest.fixture
def unverified_auth(client):
    r = client.post("/auth/register", json={"email": "fatma@example.com", "password": "supersecret1", "name": "Fatma"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access']}"}


@pytest.fixture
def auth(unverified_auth):
    """A signed-in account with a verified email (AI features need one)."""
    verify_email("fatma@example.com")
    return unverified_auth


@pytest.fixture
def fake_weather(monkeypatch):
    w = {"temp": 12.0, "feels_like": 10.0, "wind_kmh": 18.0, "code": 61, "min": 9.0, "max": 14.0, "rain_chance": 70}
    monkeypatch.setattr("app.services.orchestration.get_weather", lambda lat, lon: w)
    monkeypatch.setattr("app.routers.misc.get_weather", lambda lat, lon: w)
    return w
