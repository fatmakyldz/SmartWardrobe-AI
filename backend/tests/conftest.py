import os
import tempfile

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"
os.environ["GROQ_API_KEY"] = "test-key"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-32b"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"

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


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth(client):
    r = client.post("/auth/register", json={"email": "fatma@example.com", "password": "supersecret1", "name": "Fatma"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def fake_weather(monkeypatch):
    w = {"temp": 12.0, "feels_like": 10.0, "wind_kmh": 18.0, "code": 61, "min": 9.0, "max": 14.0, "rain_chance": 70}
    monkeypatch.setattr("app.routers.outfits.get_weather", lambda lat, lon: w)
    monkeypatch.setattr("app.routers.misc.get_weather", lambda lat, lon: w)
    return w
