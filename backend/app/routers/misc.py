from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import CityOut, WeatherOut
from ..security import current_user
from ..storage import get_storage
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
    return search_city(q, "tr" if lang == "tr" else "en")


@router.get("/images/{key:path}")
def image(key: str, db: Session = Depends(get_db)):
    """Serves images in db storage mode. Keys are random UUIDs, so links act as capabilities."""
    found = get_storage().get(db, key)
    if found is None:
        raise HTTPException(404, detail={"code": "not_found"})
    data, content_type = found
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
