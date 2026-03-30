from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WhatsAppBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Metadata(WhatsAppBaseModel):
    display_phone_number: str | None = None
    phone_number_id: str | None = None


class ContactProfile(WhatsAppBaseModel):
    name: str | None = None
    username: str | None = None


class Contact(WhatsAppBaseModel):
    profile: ContactProfile | None = None
    wa_id: str | None = None
    user_id: str | None = None
    parent_user_id: str | None = None


class MessageItem(WhatsAppBaseModel):
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    id: str | None = None
    timestamp: str | None = None
    type: str | None = None
    text: dict[str, Any] | None = None
    image: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    message_creation_type: str | None = None
    from_user_id: str | None = None
    from_parent_user_id: str | None = None


class WebhookValue(WhatsAppBaseModel):
    messaging_product: str | None = None
    metadata: Metadata | None = None
    contacts: list[Contact] = Field(default_factory=list)
    messages: list[MessageItem] = Field(default_factory=list)
    message_echoes: list[MessageItem] = Field(default_factory=list)


class WebhookChange(WhatsAppBaseModel):
    field: str | None = None
    value: WebhookValue | None = None


class WebhookEntry(WhatsAppBaseModel):
    id: str | None = None
    changes: list[WebhookChange] = Field(default_factory=list)


class WebhookEnvelope(WhatsAppBaseModel):
    object: str | None = None
    entry: list[WebhookEntry] = Field(default_factory=list)
