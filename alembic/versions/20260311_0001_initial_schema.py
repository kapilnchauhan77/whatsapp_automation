"""Initial schema for WhatsApp webhook persistence."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260311_0001"
down_revision = None
branch_labels = None
depends_on = None


UTC_NOW = sa.text("TIMEZONE('utc', NOW())")


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("object", sa.String(length=255), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_webhook_events_object", "webhook_events", ["object"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "webhook_event_id",
            sa.BigInteger(),
            sa.ForeignKey("webhook_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_id", sa.String(length=255), nullable=True),
        sa.Column("change_field", sa.String(length=50), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("whatsapp_message_id", sa.String(length=255), nullable=False),
        sa.Column("message_type", sa.String(length=64), nullable=True),
        sa.Column("wa_id", sa.String(length=64), nullable=True),
        sa.Column("sender_wa_id", sa.String(length=64), nullable=True),
        sa.Column("recipient_wa_id", sa.String(length=64), nullable=True),
        sa.Column("display_phone_number", sa.String(length=64), nullable=True),
        sa.Column("phone_number_id", sa.String(length=128), nullable=True),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("contact_username", sa.String(length=255), nullable=True),
        sa.Column("contact_user_id", sa.String(length=255), nullable=True),
        sa.Column("contact_parent_user_id", sa.String(length=255), nullable=True),
        sa.Column("from_user_id", sa.String(length=255), nullable=True),
        sa.Column("from_parent_user_id", sa.String(length=255), nullable=True),
        sa.Column("message_creation_type", sa.String(length=128), nullable=True),
        sa.Column("text_body", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_message", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("whatsapp_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint("whatsapp_message_id", name="uq_messages_whatsapp_message_id"),
    )
    op.create_index("ix_messages_wa_id", "messages", ["wa_id"], unique=False)
    op.create_index("ix_messages_whatsapp_timestamp", "messages", ["whatsapp_timestamp"], unique=False)

    op.create_table(
        "media_assets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "message_id",
            sa.BigInteger(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("whatsapp_media_id", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("sha256", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("download_status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=UTC_NOW),
        sa.UniqueConstraint("whatsapp_media_id", name="uq_media_assets_whatsapp_media_id"),
    )
    op.create_index("ix_media_assets_download_status", "media_assets", ["download_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_media_assets_download_status", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_index("ix_messages_whatsapp_timestamp", table_name="messages")
    op.drop_index("ix_messages_wa_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_webhook_events_object", table_name="webhook_events")
    op.drop_table("webhook_events")
