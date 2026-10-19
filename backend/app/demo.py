"""Demo accounts: a private sample wardrobe so visitors can try the app without signing up."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .images import normalize
from .models import Item, User
from .security import hash_password
from .storage import get_storage

ASSETS = Path(__file__).parent / "demo_assets"

# file, category, subcategory, colors, pattern, warmth, formality, seasons, name en, name tr
ALL = ["spring", "summer", "autumn", "winter"]
DEMO_ITEMS = [
    ("white-tee", "top", "t-shirt", ["white"], "solid", 1, 1, ["spring", "summer"], "White tee", "Beyaz tişört"),
    ("striped-tee", "top", "t-shirt", ["cream", "navy"], "striped", 1, 2, ["spring", "summer"], "Breton striped tee", "Çizgili tişört"),
    ("oxford-shirt", "top", "shirt", ["lightblue"], "solid", 2, 3, ALL, "Light blue oxford shirt", "Açık mavi gömlek"),
    ("cream-sweater", "top", "sweater", ["cream"], "knit", 4, 2, ["autumn", "winter"], "Cream knit sweater", "Krem triko kazak"),
    ("blue-jeans", "bottom", "jeans", ["blue"], "denim", 3, 2, ALL, "Blue jeans", "Mavi kot"),
    ("beige-chinos", "bottom", "chinos", ["beige"], "solid", 2, 3, ["spring", "summer", "autumn"], "Beige chinos", "Bej chino"),
    ("black-trousers", "bottom", "trousers", ["black"], "solid", 3, 4, ALL, "Black tailored trousers", "Siyah kumaş pantolon"),
    ("olive-skirt", "bottom", "midi skirt", ["olive"], "solid", 2, 3, ["spring", "autumn"], "Olive pleated skirt", "Haki pliseli etek"),
    ("burgundy-dress", "dress", "midi dress", ["burgundy"], "solid", 2, 4, ["autumn", "winter", "spring"], "Burgundy midi dress", "Bordo midi elbise"),
    ("navy-blazer", "outerwear", "blazer", ["navy"], "solid", 3, 4, ALL, "Navy blazer", "Lacivert blazer ceket"),
    ("camel-coat", "outerwear", "wool coat", ["brown"], "solid", 5, 4, ["autumn", "winter"], "Camel wool coat", "Camel yün kaban"),
    ("leather-jacket", "outerwear", "leather jacket", ["black"], "leather", 3, 2, ["spring", "autumn"], "Black leather jacket", "Siyah deri ceket"),
    ("white-sneakers", "shoes", "sneakers", ["white"], "leather", 2, 1, ALL, "White sneakers", "Beyaz spor ayakkabı"),
    ("brown-boots", "shoes", "chelsea boots", ["brown"], "leather", 4, 3, ["autumn", "winter"], "Brown chelsea boots", "Kahverengi bot"),
    ("black-loafers", "shoes", "loafers", ["black"], "leather", 2, 4, ["spring", "summer", "autumn"], "Black loafers", "Siyah loafer"),
    ("tan-bag", "bag", "handbag", ["brown"], "leather", 2, 3, ALL, "Tan leather bag", "Taba deri çanta"),
    ("grey-scarf", "accessory", "scarf", ["grey"], "knit", 4, 2, ["autumn", "winter"], "Grey wool scarf", "Gri yün atkı"),
]

# Istanbul, so weather-aware suggestions work immediately.
DEMO_CITY = {"en": "Istanbul", "tr": "İstanbul"}
DEMO_LAT, DEMO_LON = 41.0082, 28.9784


def create_demo_user(db: Session, locale: str) -> User:
    user = User(
        email=f"demo-{uuid.uuid4().hex[:12]}@demo.example.com",
        password_hash=hash_password(secrets.token_urlsafe(24)),  # unusable; demo users can't log in
        name="Demo",
        locale=locale,
        city=DEMO_CITY.get(locale, "Istanbul"),
        lat=DEMO_LAT,
        lon=DEMO_LON,
        is_demo=True,
        plan="demo",
    )
    db.add(user)
    db.flush()

    storage = get_storage()
    for file, cat, sub, colors, pattern, warmth, formality, seasons, name_en, name_tr in DEMO_ITEMS:
        stored, _ = normalize((ASSETS / f"{file}.png").read_bytes(), 10)
        key = f"u/{user.id.hex}/{uuid.uuid4().hex}.webp"
        storage.put(db, key, stored, "image/webp")
        db.add(
            Item(
                user_id=user.id,
                image_key=key,
                name=name_tr if locale == "tr" else name_en,
                category=cat,
                subcategory=sub,
                colors=colors,
                pattern=pattern,
                warmth=warmth,
                formality=formality,
                seasons=seasons,
            )
        )
    db.commit()
    return user


def delete_user(db: Session, user: User) -> None:
    get_storage().delete_prefix(db, f"u/{user.id.hex}/")
    db.delete(user)
    db.commit()


def cleanup_expired_demos(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=get_settings().demo_ttl_hours)
    expired = list(db.scalars(select(User).where(User.is_demo.is_(True), User.created_at < cutoff).limit(50)))
    for user in expired:
        delete_user(db, user)
    return len(expired)
