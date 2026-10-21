"""Demo accounts: a private sample wardrobe so visitors can try the app without signing up."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import FeedbackEvent, Item, Outfit, OutfitItem, User
from ..security import hash_password
from ..vocab import normalize_lang
from .images import copy_shared_image, demo_key, ensure_demo_images
from .profile import delete_account, update_style

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


def create_demo_user(db: Session, locale: str, style_profile: dict | None = None) -> User:
    locale = normalize_lang(locale)  # names and city exist in EN and TR; anything else reads the EN ones
    # The 17 pictures are shared by every demo account (§14 C5): uploaded once, never copied per visitor.
    ensure_demo_images(db, [row[0] for row in DEMO_ITEMS])
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

    for file, cat, sub, colors, pattern, warmth, formality, seasons, name_en, name_tr in DEMO_ITEMS:
        db.add(
            Item(
                user_id=user.id,
                image_key=demo_key(file),
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
    if style_profile:
        update_style(db, user, style_profile)  # onboarding answers given before the account existed (§10 step 1)
    return user


def claim_demo(db: Session, demo: User, user: User, keep_items: bool) -> dict:
    """"Set up my own wardrobe": the demo account's style profile, outfits and feedback move to the new
    account (§10 step 4). The outfits are made of demo pieces, so they come along only with keep_items,
    which copies the 17 pieces (each with its own picture, decision 15); otherwise only the profile moves.
    The demo account is deleted at the end. Returns what moved, for the response.
    Not moved: usage_counters and ai_requests.subject_id stay with the demo id (the new account starts
    the day with its own quota; the demo's spend stays pseudonymous)."""
    if not demo.is_demo:
        raise ValueError("not a demo account")
    moved = {"style_profile": False, "items": 0, "outfits": 0, "feedback_events": 0}
    if demo.style_profile:
        user.style_profile = dict(demo.style_profile)
        user.style_summary, user.style_summary_at = demo.style_summary, demo.style_summary_at
        moved["style_profile"] = True

    if keep_items:
        id_map: dict[str, uuid.UUID] = {}
        for src in list(demo.items):
            copy = Item(
                user_id=user.id, image_key=src.image_key, name=src.name, category=src.category,
                subcategory=src.subcategory, colors=list(src.colors or []), pattern=src.pattern, warmth=src.warmth,
                formality=src.formality, seasons=list(src.seasons or []), is_favorite=src.is_favorite,
                wear_count=src.wear_count, last_worn_at=src.last_worn_at,
            )
            db.add(copy)
            db.flush()
            copy_shared_image(db, user, copy)
            id_map[str(src.id)] = copy.id
        moved["items"] = len(id_map)

        for outfit in list(demo.outfits):
            outfit.user_id = user.id
            for oi in list(outfit.outfit_items):
                if str(oi.item_id) in id_map:
                    oi.item_id = id_map[str(oi.item_id)]
                else:
                    db.delete(oi)
            moved["outfits"] += 1
        events = db.scalars(select(FeedbackEvent).where(FeedbackEvent.user_id == demo.id)).all()
        for e in events:
            e.user_id = user.id
            e.item_id = id_map.get(str(e.item_id)) if e.item_id else None
        moved["feedback_events"] = len(events)
        db.flush()

    db.commit()
    db.expire(demo)  # its item/outfit collections now belong to `user`; reload before the cascade delete
    delete_account(db, demo)
    return moved


def cleanup_expired_demos(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=get_settings().demo_ttl_hours)
    expired = list(db.scalars(select(User).where(User.is_demo.is_(True), User.created_at < cutoff).limit(50)))
    for user in expired:
        delete_account(db, user)
    return len(expired)
