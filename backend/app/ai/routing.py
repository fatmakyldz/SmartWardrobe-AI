"""Routes config → ordered model chain per (feature, tier), plus a light in-memory circuit breaker.

Model ids and prices live only in routes.default.json (or the AI_ROUTES override), never in code.
"""

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from ..config import get_settings

DEFAULT_ROUTES = Path(__file__).with_name("routes.default.json")

BREAKER_FAILURES = 5  # consecutive timeouts / 5xx …
BREAKER_WINDOW_S = 300  # … within 5 minutes …
BREAKER_COOLDOWN_S = 120  # … move the provider to the end of the chain for 2 minutes


@dataclass(frozen=True)
class Candidate:
    model_class: str
    provider: str
    model: str
    in_usd_per_mtok: float
    out_usd_per_mtok: float
    options: dict = field(default_factory=dict)
    daily_cap_tokens: int | None = None

    def cost_usd_micro(self, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> int:
        # USD per million tokens == micro-USD per token. Cache reads bill at 0.1x, 5-minute writes at 1.25x.
        cost = (input_tokens + 0.1 * cache_read + 1.25 * cache_write) * self.in_usd_per_mtok
        return round(cost + output_tokens * self.out_usd_per_mtok)


@dataclass(frozen=True)
class RoutesConfig:
    models: dict[str, Candidate]
    routes: dict[str, dict[str, list[str]]]
    attempts_per_candidate: int
    timeouts_s: dict[str, float]


def parse_config(raw: dict) -> RoutesConfig:
    models = {
        name: Candidate(
            model_class=name,
            provider=m["provider"],
            model=m["model"],
            in_usd_per_mtok=float(m.get("in_usd_per_mtok", 0)),
            out_usd_per_mtok=float(m.get("out_usd_per_mtok", 0)),
            options=dict(m.get("options") or {}),
            daily_cap_tokens=m.get("daily_cap_tokens"),
        )
        for name, m in raw["models"].items()
    }
    for feature, tiers in raw["routes"].items():
        for tier, chain in tiers.items():
            unknown = [c for c in chain if c not in models]
            if unknown:
                raise ValueError(f"AI routes: {feature}/{tier} uses unknown model classes {unknown}")
    return RoutesConfig(
        models=models,
        routes=raw["routes"],
        attempts_per_candidate=int(raw.get("attempts_per_candidate", 2)),
        timeouts_s={k: float(v) for k, v in (raw.get("timeouts_s") or {}).items()},
    )


@lru_cache
def config() -> RoutesConfig:
    """AI_ROUTES may hold JSON or a path to a JSON file; otherwise routes.default.json."""
    override = get_settings().ai_routes.strip()
    if override.startswith("{"):
        raw = json.loads(override)
    else:
        raw = json.loads(Path(override or DEFAULT_ROUTES).read_text())
    return parse_config(raw)


class Health:
    """Per-process provider health and per-model daily token use (single instance, so memory is enough)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self._failures: dict[str, list[float]] = {}
        self._demoted_until: dict[str, float] = {}
        self._tokens: dict[tuple[str, str], int] = {}

    def failure(self, provider: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            recent = [t for t in self._failures.get(provider, []) if now - t <= BREAKER_WINDOW_S] + [now]
            self._failures[provider] = recent
            if len(recent) >= BREAKER_FAILURES:
                self._demoted_until[provider] = now + BREAKER_COOLDOWN_S
                self._failures[provider] = []

    def success(self, provider: str) -> None:
        with self._lock:
            self._failures.pop(provider, None)

    def demoted(self, provider: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return self._demoted_until.get(provider, 0) > now

    def add_tokens(self, model_class: str, tokens: int) -> None:
        key = (model_class, datetime.now(timezone.utc).date().isoformat())
        with self._lock:
            self._tokens[key] = self._tokens.get(key, 0) + tokens

    def over_cap(self, c: Candidate) -> bool:
        if not c.daily_cap_tokens:
            return False
        key = (c.model_class, datetime.now(timezone.utc).date().isoformat())
        return self._tokens.get(key, 0) >= c.daily_cap_tokens


HEALTH = Health()


def chain(feature: str, tier: str) -> list[Candidate]:
    cfg = config()
    tiers = cfg.routes.get(feature) or {}
    names = tiers.get(tier) or tiers.get("standard") or []
    candidates = [cfg.models[n] for n in names]
    candidates = [c for c in candidates if not HEALTH.over_cap(c)]
    # Healthy providers first, keeping config order; demoted ones stay as a last resort.
    return sorted(candidates, key=lambda c: HEALTH.demoted(c.provider))


def timeout_for(feature: str, default: float) -> float:
    return config().timeouts_s.get(feature, default)


def attempts_per_candidate() -> int:
    return config().attempts_per_candidate
