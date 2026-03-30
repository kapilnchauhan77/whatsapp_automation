from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    object_type: Mapped[str | None] = mapped_column("object", String(255), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    messages: Mapped[list["Message"]] = relationship(back_populates="webhook_event", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    webhook_event_id: Mapped[int] = mapped_column(ForeignKey("webhook_events.id", ondelete="CASCADE"), nullable=False)
    entry_id: Mapped[str | None] = mapped_column(String(255))
    change_field: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    whatsapp_message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    message_type: Mapped[str | None] = mapped_column(String(64))
    wa_id: Mapped[str | None] = mapped_column(String(64), index=True)
    sender_wa_id: Mapped[str | None] = mapped_column(String(64))
    recipient_wa_id: Mapped[str | None] = mapped_column(String(64))
    display_phone_number: Mapped[str | None] = mapped_column(String(64))
    phone_number_id: Mapped[str | None] = mapped_column(String(128))
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_username: Mapped[str | None] = mapped_column(String(255))
    contact_user_id: Mapped[str | None] = mapped_column(String(255))
    contact_parent_user_id: Mapped[str | None] = mapped_column(String(255))
    from_user_id: Mapped[str | None] = mapped_column(String(255))
    from_parent_user_id: Mapped[str | None] = mapped_column(String(255))
    message_creation_type: Mapped[str | None] = mapped_column(String(128))
    text_body: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    context_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_message: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    whatsapp_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    webhook_event: Mapped[WebhookEvent] = relationship(back_populates="messages")
    media_assets: Mapped[list["MediaAsset"]] = relationship(back_populates="message", cascade="all, delete-orphan")


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    media_type: Mapped[str] = mapped_column(String(64), nullable=False)
    whatsapp_media_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    sha256: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(Text)
    download_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    message: Mapped[Message] = relationship(back_populates="media_assets")


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_wa_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255))
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    avg_price: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_wa_id", "symbol", name="uq_portfolio_user_symbol"),
    )

    transactions: Mapped[list["PortfolioTransaction"]] = relationship(back_populates="holding", cascade="all, delete-orphan")


class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    holding_id: Mapped[int] = mapped_column(ForeignKey("portfolio_holdings.id", ondelete="CASCADE"), nullable=False)
    user_wa_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # "buy" or "sell"
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price_per_share: Mapped[float] = mapped_column(Float, nullable=False)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)

    holding: Mapped[PortfolioHolding] = relationship(back_populates="transactions")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
