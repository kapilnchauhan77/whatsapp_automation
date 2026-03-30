from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from whatsapp_automation.models import MediaAsset, Message, WebhookEvent
from whatsapp_automation.schemas import Contact, MessageItem, Metadata, WebhookEnvelope, WebhookValue


def persist_webhook(session: Session, payload: WebhookEnvelope) -> list[int]:
    payload_dict = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
    webhook_event = WebhookEvent(
        object_type=payload.object,
        raw_payload=payload_dict,
    )
    session.add(webhook_event)
    session.flush()

    media_asset_ids: list[int] = []

    for entry in payload.entry:
        for change in entry.changes:
            if change.field not in {"messages", "message_echoes"} or change.value is None:
                continue

            direction = "inbound" if change.field == "messages" else "outbound_echo"
            message_items = change.value.messages if change.field == "messages" else change.value.message_echoes

            for item in message_items:
                if not item.id:
                    continue

                message = session.scalar(
                    select(Message).where(Message.whatsapp_message_id == item.id)
                )
                if message is None:
                    message = _build_message(
                        webhook_event=webhook_event,
                        entry_id=entry.id,
                        change_field=change.field,
                        direction=direction,
                        value=change.value,
                        item=item,
                    )
                    session.add(message)
                    session.flush()

                media_asset = _ensure_media_asset(session=session, message=message, item=item)
                if media_asset is not None:
                    media_asset_ids.append(media_asset.id)

    return media_asset_ids


def _build_message(
    webhook_event: WebhookEvent,
    entry_id: str | None,
    change_field: str,
    direction: str,
    value: WebhookValue,
    item: MessageItem,
) -> Message:
    contact = value.contacts[0] if value.contacts else None
    metadata = value.metadata
    message_dict = item.model_dump(mode="json", by_alias=True, exclude_none=True)

    return Message(
        webhook_event_id=webhook_event.id,
        entry_id=entry_id,
        change_field=change_field,
        direction=direction,
        whatsapp_message_id=item.id,
        message_type=item.type,
        wa_id=_primary_wa_id(change_field=change_field, item=item, contact=contact),
        sender_wa_id=item.from_,
        recipient_wa_id=item.to if item.to else _recipient_fallback(direction=direction, metadata=metadata),
        display_phone_number=metadata.display_phone_number if metadata else None,
        phone_number_id=metadata.phone_number_id if metadata else None,
        contact_name=contact.profile.name if contact and contact.profile else None,
        contact_username=contact.profile.username if contact and contact.profile else None,
        contact_user_id=contact.user_id if contact else None,
        contact_parent_user_id=contact.parent_user_id if contact else None,
        from_user_id=item.from_user_id,
        from_parent_user_id=item.from_parent_user_id,
        message_creation_type=item.message_creation_type,
        text_body=_extract_text_body(item),
        caption=_extract_caption(message_dict),
        context_json=item.context,
        raw_message=message_dict,
        whatsapp_timestamp=_parse_whatsapp_timestamp(item.timestamp),
    )


def _ensure_media_asset(session: Session, message: Message, item: MessageItem) -> MediaAsset | None:
    if item.type != "image":
        return None

    image_data = item.image or {}
    media_id = image_data.get("id")

    query = select(MediaAsset).where(MediaAsset.message_id == message.id, MediaAsset.media_type == "image")
    if media_id:
        query = select(MediaAsset).where(MediaAsset.whatsapp_media_id == media_id)

    existing_asset = session.scalar(query)
    if existing_asset is not None:
        if existing_asset.download_status != "downloaded" or not existing_asset.storage_path:
            existing_asset.source_url = image_data.get("url") or existing_asset.source_url
            existing_asset.mime_type = image_data.get("mime_type") or existing_asset.mime_type
            existing_asset.sha256 = image_data.get("sha256") or existing_asset.sha256
            if media_id:
                existing_asset.whatsapp_media_id = media_id
            return existing_asset
        return None

    media_asset = MediaAsset(
        message_id=message.id,
        media_type="image",
        whatsapp_media_id=media_id,
        mime_type=image_data.get("mime_type"),
        sha256=image_data.get("sha256"),
        source_url=image_data.get("url"),
        download_status="pending",
    )
    session.add(media_asset)
    session.flush()
    return media_asset


def _primary_wa_id(change_field: str, item: MessageItem, contact: Contact | None) -> str | None:
    if change_field == "message_echoes":
        return item.to or (contact.wa_id if contact else None) or item.from_
    return item.from_ or (contact.wa_id if contact else None)


def _recipient_fallback(direction: str, metadata: Metadata | None) -> str | None:
    if direction == "inbound" and metadata:
        return metadata.display_phone_number
    return None


def _extract_text_body(item: MessageItem) -> str | None:
    if item.type == "text" and item.text:
        return item.text.get("body")
    return None


def _extract_caption(message_dict: dict[str, object]) -> str | None:
    message_type = message_dict.get("type")
    if isinstance(message_type, str):
        message_payload = message_dict.get(message_type)
        if isinstance(message_payload, dict):
            caption = message_payload.get("caption")
            if isinstance(caption, str):
                return caption
    return None


def _parse_whatsapp_timestamp(timestamp: str | None) -> datetime | None:
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
    except (TypeError, ValueError):
        return None
