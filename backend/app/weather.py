"""Open-Meteo (free, no API key): current weather + today's range, and city search."""

import time

import httpx
from fastapi import HTTPException

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

_cache: dict[tuple, tuple[float, dict]] = {}
TTL = 15 * 60


def _get(url: str, params: dict) -> dict:
    try:
        r = httpx.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError:
        raise HTTPException(502, detail={"code": "weather_unavailable"})


def get_weather(lat: float, lon: float) -> dict:
    key = (round(lat, 2), round(lon, 2))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]

    data = _get(
        FORECAST_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "timezone": "auto",
            "forecast_days": 1,
        },
    )
    cur, day = data.get("current", {}), data.get("daily", {})

    def first(name):
        values = day.get(name) or [None]
        return values[0]

    result = {
        "temp": cur.get("temperature_2m"),
        "feels_like": cur.get("apparent_temperature"),
        "wind_kmh": cur.get("wind_speed_10m"),
        "code": cur.get("weather_code"),
        "min": first("temperature_2m_min"),
        "max": first("temperature_2m_max"),
        "rain_chance": first("precipitation_probability_max"),
    }
    _cache[key] = (time.time(), result)
    return result


def search_city(q: str, lang: str) -> list[dict]:
    data = _get(GEOCODE_URL, {"name": q, "count": 6, "language": lang, "format": "json"})
    out = []
    for r in data.get("results") or []:
        parts = [r.get("name"), r.get("admin1"), r.get("country")]
        out.append(
            {
                "name": r.get("name"),
                "label": ", ".join(p for p in parts if p),
                "lat": r.get("latitude"),
                "lon": r.get("longitude"),
            }
        )
    return out


# WMO weather codes → a short English description the LLM understands.
def describe(code: int | None) -> str:
    if code is None:
        return "unknown"
    if code == 0:
        return "clear sky"
    if code in (1, 2):
        return "partly cloudy"
    if code == 3:
        return "overcast"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 57:
        return "drizzle"
    if 61 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if code >= 95:
        return "thunderstorm"
    return "mixed"
