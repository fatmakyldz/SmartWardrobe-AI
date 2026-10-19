from sqlalchemy import select

from app.db import SessionLocal
from app.models import User, WardrobeImage


def _user(email: str, demo: bool = False) -> User:
    return User(email=email, password_hash="x", is_demo=demo)


def _img(key: str, owner: User | None) -> WardrobeImage:
    return WardrobeImage(key=key, user_id=owner.id if owner else None, content_type="image/webp",
                         bytes=1, width=1, height=1)


def test_shared_null_owner_images_are_visible_only_to_demo_accounts():
    with SessionLocal() as db:
        normal, other, demo = _user("a@example.com"), _user("b@example.com"), _user("demo@example.com", demo=True)
        db.add_all([normal, other, demo])
        db.flush()
        db.add_all([
            _img("u/a/1.webp", normal), _img("u/b/1.webp", other), _img("u/demo/1.webp", demo),
            _img("demo/tee.webp", None), _img("demo/jeans.webp", None),
        ])
        db.commit()

        def keys(user: User) -> set[str]:
            return set(db.scalars(select(WardrobeImage.key).where(WardrobeImage.visible_to(user))))

        assert keys(normal) == {"u/a/1.webp"}
        assert keys(other) == {"u/b/1.webp"}
        assert keys(demo) == {"u/demo/1.webp", "demo/tee.webp", "demo/jeans.webp"}
        assert not any(k.startswith("demo/") for k in keys(normal) | keys(other))
