import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Lang = Literal["en", "tr"]
Category = Literal["top", "bottom", "dress", "outerwear", "shoes", "accessory", "bag"]
Occasion = Literal["casual", "work", "formal", "date", "sport", "party", "travel"]


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=80)
    locale: Lang = "en"


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class DemoIn(BaseModel):
    locale: Lang = "en"


class AuthOut(BaseModel):
    access: str  # 15-minute JWT
    refresh: str | None  # 30 days, single use; None on the web, where it is set as an httpOnly cookie
    user: "UserOut"


class RefreshIn(BaseModel):
    refresh: str | None = Field(default=None, max_length=200)  # omitted on the web: read from the cookie


class TokenIn(BaseModel):
    token: str = Field(max_length=200)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    locale: str
    city: str
    lat: float | None
    lon: float | None
    is_demo: bool
    email_verified_at: datetime | None


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    locale: Lang | None = None
    city: str | None = Field(default=None, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class Tags(BaseModel):
    name: str = Field(default="", max_length=120)
    category: Category
    subcategory: str = Field(default="", max_length=60)
    colors: list[str] = Field(default_factory=list, max_length=3)
    pattern: str = "solid"
    warmth: int = Field(default=3, ge=1, le=5)
    formality: int = Field(default=2, ge=1, le=5)
    seasons: list[str] = Field(default_factory=list, max_length=4)


class AnalyzeOut(BaseModel):
    image_key: str
    image_url: str
    is_clothing: bool
    tags: Tags
    ai_skipped: str | None = None  # "email_unverified": photo stored, tags left for the user


class ItemIn(Tags):
    image_key: str = Field(max_length=120)


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    category: Category | None = None
    subcategory: str | None = Field(default=None, max_length=60)
    colors: list[str] | None = Field(default=None, max_length=3)
    pattern: str | None = None
    warmth: int | None = Field(default=None, ge=1, le=5)
    formality: int | None = Field(default=None, ge=1, le=5)
    seasons: list[str] | None = Field(default=None, max_length=4)


class ItemOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    subcategory: str
    colors: list[str]
    pattern: str
    warmth: int
    formality: int
    seasons: list[str]
    image_key: str  # stable: the app's image cache key (image_url is a fresh short-lived link each time)
    image_url: str
    created_at: datetime


class WeatherOut(BaseModel):
    temp: float | None
    feels_like: float | None
    wind_kmh: float | None
    code: int | None
    min: float | None
    max: float | None
    rain_chance: float | None


class CityOut(BaseModel):
    name: str | None
    label: str
    lat: float
    lon: float


class SuggestIn(BaseModel):
    occasion: Occasion = "casual"
    note: str = Field(default="", max_length=200)
    # Free text ("something warm for a client lunch, no dress"): parsed by the intent feature first (one
    # extra AI request); its occasion wins over `occasion` when it names one.
    request: str | None = Field(default=None, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    lang: Lang = "en"


class IntentIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    lang: Lang = "en"

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("text is blank")
        return v


class IntentOut(BaseModel):
    """A natural-language request as vocabulary values (AI-06)."""

    occasion: Occasion | None
    include_categories: list[Category]
    include_colors: list[str]
    avoid_categories: list[Category]
    avoid_colors: list[str]
    avoid_patterns: list[str]
    wants_outerwear: bool | None
    brief: str


class OutfitOut(BaseModel):
    id: uuid.UUID
    title: str
    reason: str
    occasion: str
    note: str
    weather: dict
    rating: int
    items: list[ItemOut]
    created_at: datetime


class SuggestOut(BaseModel):
    weather: WeatherOut | None
    outfits: list[OutfitOut]
    intent: IntentOut | None = None  # set when the request was given as free text


class GapOut(BaseModel):
    """Something the wardrobe is missing; the app translates `code` (see ai/analysis.py GAP_CODES)."""

    code: str
    category: Category | None = None
    occasion: Occasion | None = None
    season: str | None = None
    severity: int
    item_ids: list[uuid.UUID] = []


class WardrobeAnalysisOut(BaseModel):
    season: str
    items: int
    per_category: dict[str, int]
    outfits_possible: int
    neutral_share: float
    gaps: list[GapOut]


class CapsuleIn(BaseModel):
    occasions: list[Occasion] = Field(default=["casual", "work"], min_length=1, max_length=7)
    size: int = Field(default=12, ge=6, le=20)
    lang: Lang = "en"
    explain: bool = True  # False: the deterministic capsule only, no AI request spent
    lat: float | None = Field(default=None, ge=-90, le=90)  # for the season (hemisphere)


class CapsuleOut(BaseModel):
    occasions: list[Occasion]
    season: str
    items: list[ItemOut]
    outfits_possible: int
    sample_outfits: list[list[uuid.UUID]]
    gaps: list[GapOut]
    summary: str | None = None
    tips: list[str] = []


class FeedbackIn(BaseModel):
    rating: Literal[-1, 0, 1]


class OutfitCreateIn(BaseModel):
    item_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)
    occasion: Occasion = "casual"
    title: str = Field(default="", max_length=120)
    lang: Lang = "en"


class OutfitItemsIn(BaseModel):
    item_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)


Color = Literal["black", "white", "grey", "navy", "blue", "lightblue", "green", "olive", "beige", "cream", "brown",
                "khaki", "red", "burgundy", "pink", "purple", "yellow", "orange", "gold", "silver", "multi"]
Style = Literal["minimal", "classic", "casual", "bold", "sporty", "romantic", "streetwear", "boho"]
Palette = Literal["neutral", "dark", "vivid", "pastel"]
Priority = Literal["comfort", "elegance", "weather", "variety"]
Avoidable = Literal["solid", "striped", "checked", "floral", "printed", "denim", "knit", "leather", "other",
                    "top", "bottom", "dress", "outerwear", "shoes", "accessory", "bag"]


class StyleAnswers(BaseModel):
    q1: Style | None = None  # overall style
    q2: list[Palette] | None = Field(default=None, max_length=4)  # colour world
    q3: Priority | None = None  # what matters most when choosing


class StyleIn(BaseModel):
    """Only fixed vocabularies, so nothing free-form ever reaches a prompt."""

    answers: StyleAnswers | None = None
    liked_colors: list[Color] | None = Field(default=None, max_length=8)
    disliked_colors: list[Color] | None = Field(default=None, max_length=8)
    styles: list[Style] | None = Field(default=None, max_length=4)
    avoid: list[Avoidable] | None = Field(default=None, max_length=8)


class StyleOut(BaseModel):
    answers: dict = Field(default_factory=dict)
    liked_colors: list[str] = Field(default_factory=list)
    disliked_colors: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    summary: str | None = None


class VocabOut(BaseModel):
    categories: list[str]
    colors: list[str]
    patterns: list[str]
    seasons: list[str]
    occasions: list[str]
    styles: list[str]
    palettes: list[str]
    priorities: list[str]


AuthOut.model_rebuild()
