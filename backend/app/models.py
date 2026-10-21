import uuid
from datetime import date, datetime, timezone
from typing import Literal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    or_,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Enum-like columns are plain strings in the DB (no DB enum types); these Literals document the values.
OutfitSource = Literal["ai", "user", "ai_edited"]
FeedbackKind = Literal["like", "dislike", "unrate", "worn", "skip"]
AIRequestStatus = Literal["ok", "fallback", "error", "budget"]
AIAttemptStatus = Literal["ok", "timeout", "rate_limited", "bad_output", "error"]
AuthTokenPurpose = Literal["verify_email", "reset_password"]
SubscriptionStatus = Literal["active", "trialing", "past_due", "canceled"]
GrantSource = Literal["promo", "support", "tester", "manual"]


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(80), default="")
    locale: Mapped[str] = mapped_column(String(5), default="en")
    city: Mapped[str] = mapped_column(String(120), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # {answers: {q1, q2, q3}, liked_colors: [], disliked_colors: [], styles: [], avoid: []}
    style_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    style_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_summary_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    plan: Mapped[str] = mapped_column(String(20), default="free", server_default="free")  # denormalized; source: subscriptions
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)  # IANA name
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    items: Mapped[list["Item"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    outfits: Mapped[list["Outfit"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    image_key: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(120), default="")
    category: Mapped[str] = mapped_column(String(20), index=True)
    subcategory: Mapped[str] = mapped_column(String(60), default="")
    colors: Mapped[list[str]] = mapped_column(JSON, default=list)
    pattern: Mapped[str] = mapped_column(String(20), default="solid")
    warmth: Mapped[int] = mapped_column(Integer, default=3)  # 1 = very light … 5 = very warm
    formality: Mapped[int] = mapped_column(Integer, default=2)  # 1 = sporty/lounge … 5 = black tie
    seasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    brand: Mapped[str] = mapped_column(String(80), default="", server_default="")
    material: Mapped[str] = mapped_column(String(40), default="", server_default="")
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    wear_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_worn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Tags as the model gave them, after schema + vocab checks, before the user's edits.
    ai_tags_raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_requests.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="items")
    outfit_items: Mapped[list["OutfitItem"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", passive_deletes=True
    )
    wardrobe_image: Mapped["WardrobeImage | None"] = relationship(back_populates="item", passive_deletes=True)


class Outfit(Base):
    __tablename__ = "outfits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    occasion: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(200), default="")
    weather: Mapped[dict] = mapped_column(JSON, default=dict)
    title: Mapped[str] = mapped_column(String(120), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    lang: Mapped[str] = mapped_column(String(5), default="en")
    rating: Mapped[int] = mapped_column(Integer, default=0)  # -1 dislike, 0 none, 1 like (latest state)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(20), default="ai", server_default="ai")  # OutfitSource
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ai_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_requests.id", ondelete="SET NULL"), nullable=True
    )
    worn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="outfits")
    # The pieces of the outfit, in position order (the only source since 0004_cleanup).
    outfit_items: Mapped[list["OutfitItem"]] = relationship(
        back_populates="outfit", cascade="all, delete-orphan", passive_deletes=True, order_by="OutfitItem.position"
    )


class OutfitItem(Base):
    __tablename__ = "outfit_items"

    outfit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("outfits.id", ondelete="CASCADE"), primary_key=True)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True, index=True)
    position: Mapped[int] = mapped_column(Integer)
    slot: Mapped[str] = mapped_column(String(20))  # the item's category: top, bottom, dress, …

    outfit: Mapped[Outfit] = relationship(back_populates="outfit_items")
    item: Mapped[Item] = relationship(back_populates="outfit_items")


class AIRequest(Base):
    """One logical AI request. No prompt or output text is stored."""

    __tablename__ = "ai_requests"
    __table_args__ = (
        Index("ix_ai_requests_subject_id_created_at", "subject_id", "created_at"),
        Index("ix_ai_requests_feature_created_at", "feature", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Pseudonymous users.id, deliberately without a foreign key; nulled after 90 days.
    subject_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    feature: Mapped[str] = mapped_column(String(40))
    prompt_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))  # AIRequestStatus
    final_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    final_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    final_model_class: Mapped[str | None] = mapped_column(String(40), nullable=True)
    input_tokens_total: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens_total: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd_micro_total: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms_total: Mapped[int] = mapped_column(Integer, default=0)
    attempts_count: Mapped[int] = mapped_column(Integer, default=0)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The gateway's pre-call input estimate, kept to calibrate it against input_tokens_total.
    estimated_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    attempts: Mapped[list["AIRequestAttempt"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", passive_deletes=True, order_by="AIRequestAttempt.attempt_no"
    )


class AIRequestAttempt(Base):
    """One provider call (retries and fallbacks included)."""

    __tablename__ = "ai_request_attempts"
    __table_args__ = (
        UniqueConstraint("request_id", "attempt_no"),
        Index("ix_ai_request_attempts_provider_created_at", "provider", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_requests.id", ondelete="CASCADE"))
    attempt_no: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20))  # AIAttemptStatus
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd_micro: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request: Mapped[AIRequest] = relationship(back_populates="attempts")


class FeedbackEvent(Base):
    __tablename__ = "feedback_events"
    __table_args__ = (Index("ix_feedback_events_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    outfit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("outfits.id", ondelete="SET NULL"), nullable=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # FeedbackKind
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WardrobeImage(Base):
    """Metadata for an object in the image bucket. attached_at NULL = orphan (not on an item yet)."""

    __tablename__ = "wardrobe_images"
    __table_args__ = (
        Index(
            "ix_wardrobe_images_attached_at",
            "attached_at",
            postgresql_where=text("attached_at IS NULL"),
        ),
    )

    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    # NULL for shared system objects (demo images, §8).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("items.id", ondelete="SET NULL"), nullable=True)
    content_type: Mapped[str] = mapped_column(String(40))
    bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    attached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    item: Mapped[Item | None] = relationship(back_populates="wardrobe_image")

    @classmethod
    def visible_to(cls, user: User):
        """WHERE clause for listing a user's images. Shared (user_id NULL) demo images are visible to
        demo accounts only; every list query over this table must use it."""
        if user.is_demo:
            return or_(cls.user_id == user.id, cls.user_id.is_(None))
        return cls.user_id == user.id


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 hex; the raw token is never stored
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    device_label: Mapped[str] = mapped_column(String(120), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthToken(Base):
    """Single-use email verification / password reset tokens."""

    __tablename__ = "auth_tokens"
    __table_args__ = (Index("ix_auth_tokens_user_id_purpose", "user_id", "purpose"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(20))  # AuthTokenPurpose
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Subscription(Base):
    """Plan state, independent of the payment provider."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_user_id_status", "user_id", "status"),
        Index(
            "uq_subscriptions_provider_ref",
            "provider",
            "provider_ref",
            unique=True,
            postgresql_where=text("provider_ref IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    plan: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))  # SubscriptionStatus
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)  # manual / apple / google / stripe
    provider_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UsageCounter(Base):
    __tablename__ = "usage_counters"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    feature: Mapped[str] = mapped_column(String(40), primary_key=True)
    period_start: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)


class EntitlementGrant(Base):
    """Rights outside a subscription: promo, gifted premium, testers, support decisions."""

    __tablename__ = "entitlement_grants"
    __table_args__ = (
        Index("ix_entitlement_grants_user_id_ends_at", "user_id", "ends_at"),
        CheckConstraint(
            "plan_override IS NOT NULL OR feature IS NOT NULL OR limits IS NOT NULL",
            name="ck_entitlement_grants_grants_something",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    plan_override: Mapped[str | None] = mapped_column(String(20), nullable=True)
    feature: Mapped[str | None] = mapped_column(String(40), nullable=True)
    limits: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(20))  # GrantSource
    reason: Mapped[str] = mapped_column(String(200), default="")  # free text, no PII
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # NULL = no end
    created_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
