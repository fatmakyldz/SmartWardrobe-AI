"""DTOs going into ai.context. Plain data: no ORM objects, no sessions."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ItemDTO:
    id: uuid.UUID
    category: str
    subcategory: str
    colors: tuple[str, ...]
    pattern: str
    warmth: int
    formality: int
    seasons: tuple[str, ...]
    created_at: datetime
    is_favorite: bool = False
    last_worn_at: datetime | None = None
    archived: bool = False


@dataclass(frozen=True)
class WeatherDTO:
    temp: float | None = None
    feels_like: float | None = None
    wind_kmh: float | None = None
    code: int | None = None
    min: float | None = None
    max: float | None = None
    rain_chance: float | None = None


@dataclass(frozen=True)
class StyleProfileDTO:
    styles: tuple[str, ...] = ()  # onboarding Q1 + explicit styles
    palettes: tuple[str, ...] = ()  # Q2
    priority: str | None = None  # Q3
    liked_colors: tuple[str, ...] = ()
    disliked_colors: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeedbackDTO:
    kind: str  # like / dislike / worn
    pieces: tuple[tuple[str, str], ...]  # (category, main colour) per item, no ids


@dataclass(frozen=True)
class IntentDTO:
    """Parsed natural-language request (AI-06): vocabulary values only, plus a one-line English brief."""

    occasion: str | None = None
    include_categories: tuple[str, ...] = ()
    include_colors: tuple[str, ...] = ()
    avoid_categories: tuple[str, ...] = ()
    avoid_colors: tuple[str, ...] = ()
    avoid_patterns: tuple[str, ...] = ()
    wants_outerwear: bool | None = None
    brief: str = ""

    @property
    def has_avoids(self) -> bool:
        return bool(self.avoid_categories or self.avoid_colors or self.avoid_patterns)


@dataclass(frozen=True)
class ContextLimits:
    category_caps: dict = field(default_factory=lambda: {
        "top": 20, "bottom": 12, "dress": 8, "outerwear": 8, "shoes": 8, "bag": 5, "accessory": 8})
    note_chars: int = 200
    recent_feedback: int = 5
    hot_feels_like: float = 24  # above: drop warmth >= 4
    cold_feels_like: float = 8  # below: drop warmth <= 1


DEFAULT_LIMITS = ContextLimits()


@dataclass(frozen=True)
class CapsuleContext:
    """What the model sees when asked to explain a deterministic capsule (AI-06)."""

    text: str
    item_ids: tuple[uuid.UUID, ...]
    estimated_tokens: int


@dataclass(frozen=True)
class SuggestContext:
    text: str  # the user message
    items: tuple[ItemDTO, ...]  # kept items; position = the index the model sees
    index_to_item_id: dict[int, uuid.UUID]
    items_dropped_count: int
    relaxed: tuple[str, ...]  # filters dropped to keep a complete outfit possible
    season: str
    estimated_tokens: int
