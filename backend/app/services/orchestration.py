"""Collects what a suggestion needs and hands it over as ai.context DTOs.

The one bridge between services and app.ai (docs §1): it reads, it never writes, and ai.context never
calls back into services.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.schemas.context import FeedbackDTO, ItemDTO, StyleProfileDTO, WeatherDTO
from ..models import FeedbackEvent, Item, Outfit, User
from ..weather import get_weather
from .profile import aware, outfit_items

RECENT_EVENTS = 5
RECENTLY_WORN_DAYS = 7


@dataclass(frozen=True)
class SuggestInputs:
    items: list[ItemDTO]
    weather: dict | None  # as stored on the outfit and returned to the app
    weather_dto: WeatherDTO | None
    profile: StyleProfileDTO
    summary: str | None
    recent_feedback: list[FeedbackDTO]
    recently_worn: list
    southern_hemisphere: bool


def item_dto(i: Item) -> ItemDTO:
    return ItemDTO(id=i.id, category=i.category, subcategory=i.subcategory or "", colors=tuple(i.colors or ()),
                   pattern=i.pattern, warmth=i.warmth, formality=i.formality, seasons=tuple(i.seasons or ()),
                   created_at=aware(i.created_at), is_favorite=bool(i.is_favorite),
                   last_worn_at=aware(i.last_worn_at), archived=i.archived_at is not None)


def style_profile_dto(raw: dict | None) -> StyleProfileDTO:
    raw = raw or {}
    answers = raw.get("answers") or {}
    styles = [answers.get("q1")] if answers.get("q1") else []
    styles += [s for s in raw.get("styles") or [] if s not in styles]
    return StyleProfileDTO(styles=tuple(styles), palettes=tuple(answers.get("q2") or ()),
                           priority=answers.get("q3"), liked_colors=tuple(raw.get("liked_colors") or ()),
                           disliked_colors=tuple(raw.get("disliked_colors") or ()), avoid=tuple(raw.get("avoid") or ()))


def _weather(lat: float | None, lon: float | None) -> dict | None:
    if lat is None or lon is None:
        return None
    try:
        return get_weather(lat, lon)
    except HTTPException:
        return None  # still suggest something without weather


@dataclass(frozen=True)
class WardrobeInputs:
    items: list[ItemDTO]
    southern_hemisphere: bool


def wardrobe_inputs(user: User, lat: float | None = None) -> WardrobeInputs:
    """The wardrobe as DTOs for the deterministic analysis (ai.analysis): no weather, no history."""
    lat = lat if lat is not None else user.lat
    return WardrobeInputs(items=[item_dto(i) for i in user.items], southern_hemisphere=lat is not None and lat < 0)


def suggest_inputs(db: Session, user: User, lat: float | None, lon: float | None, now: datetime) -> SuggestInputs:
    lat = lat if lat is not None else user.lat
    lon = lon if lon is not None else user.lon
    weather = _weather(lat, lon)

    events = db.scalars(
        select(FeedbackEvent)
        .where(FeedbackEvent.user_id == user.id, FeedbackEvent.kind.in_(("like", "dislike", "worn")),
               FeedbackEvent.outfit_id.is_not(None))
        .order_by(FeedbackEvent.created_at.desc())
        .limit(RECENT_EVENTS)
    ).all()
    recent = []
    for e in events:
        outfit = db.get(Outfit, e.outfit_id)
        if outfit is not None:
            pieces = tuple((i.category, (i.colors or [""])[0]) for i in outfit_items(db, outfit))
            recent.append(FeedbackDTO(kind=e.kind, pieces=pieces))

    items = list(user.items)
    cutoff = now - timedelta(days=RECENTLY_WORN_DAYS)
    return SuggestInputs(
        items=[item_dto(i) for i in items],
        weather=weather,
        weather_dto=WeatherDTO(**{k: weather.get(k) for k in WeatherDTO.__dataclass_fields__}) if weather else None,
        profile=style_profile_dto(user.style_profile),
        summary=user.style_summary,
        recent_feedback=recent,
        recently_worn=[i.id for i in items if i.last_worn_at and aware(i.last_worn_at) >= cutoff],
        southern_hemisphere=lat is not None and lat < 0,
    )
