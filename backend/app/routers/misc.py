from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User
from ..schemas import CityOut, VocabOut, WeatherOut
from ..security import current_user
from ..services import images
from ..storage import cache_control, get_storage
from ..vocab import CATEGORIES, COLORS, OCCASIONS, PALETTES, PATTERNS, PRIORITIES, SEASONS, STYLES, normalize_lang
from ..weather import get_weather, search_city

router = APIRouter(tags=["misc"])


@router.get("/weather", response_model=WeatherOut)
def weather(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    _: User = Depends(current_user),
):
    return get_weather(lat, lon)


@router.get("/cities", response_model=list[CityOut])
def cities(q: str = Query(min_length=2, max_length=80), lang: str = "en", _: User = Depends(current_user)):
    return search_city(q, normalize_lang(lang))


@router.get("/images/{key:path}")
def image(key: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Serves images in db storage mode, to their owner only (shared demo pictures: demo accounts).
    With the bucket (STORAGE_BACKEND=s3) it is closed: image_url is a presigned link instead."""
    if get_settings().storage_backend == "s3" or not images.can_view(user, key):
        raise HTTPException(404, detail={"code": "not_found"})
    found = get_storage().get(db, key)
    if found is None:
        raise HTTPException(404, detail={"code": "not_found"})
    data, content_type = found
    return Response(content=data, media_type=content_type, headers={"Cache-Control": cache_control()})


@router.get("/meta/vocab", response_model=VocabOut)
def vocab():
    """The fixed vocabularies, so the app no longer keeps its own copy (wired in AI-07)."""
    return VocabOut(categories=CATEGORIES, colors=COLORS, patterns=PATTERNS, seasons=SEASONS, occasions=OCCASIONS,
                    styles=STYLES, palettes=PALETTES, priorities=PRIORITIES)
