from __future__ import annotations

from html import escape
import logging
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from whatsapp_automation.config import Settings, get_settings
from whatsapp_automation.db import configure_engine, get_session
from whatsapp_automation.ingest import persist_webhook
from whatsapp_automation.media import get_retryable_media_asset_ids, process_media_downloads
from whatsapp_automation.messaging import process_with_agent
from whatsapp_automation.models import MediaAsset, Message
from whatsapp_automation.schemas import WebhookEnvelope


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(settings)
    settings.media_storage_root.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        configure_engine(settings.database_url)
        settings.media_storage_root.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(title="WhatsApp Automation Webhook", lifespan=lifespan)
    app.mount("/media", StaticFiles(directory=str(settings.media_storage_root), check_dir=False), name="media")

    @app.get("/", response_class=Response)
    def verify_webhook(
        mode: str | None = Query(default=None, alias="hub.mode"),
        challenge: str | None = Query(default=None, alias="hub.challenge"),
        token: str | None = Query(default=None, alias="hub.verify_token"),
        current_settings: Settings = Depends(get_settings),
    ) -> Response:
        if mode == "subscribe" and token == current_settings.whatsapp_verify_token and challenge is not None:
            logging.getLogger(__name__).info("Webhook verified successfully.")
            return Response(content=challenge, status_code=200, media_type="text/plain")
        return Response(status_code=403)

    @app.post("/", response_class=Response)
    def receive_webhook(
        payload: WebhookEnvelope,
        background_tasks: BackgroundTasks,
        session: Session = Depends(get_session),
    ) -> Response:
        logger = logging.getLogger(__name__)
        logger.info("Webhook received.")
        media_asset_ids: list[int] = []

        try:
            media_asset_ids = persist_webhook(session=session, payload=payload)
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            logger.exception("Failed to persist webhook payload.")
            raise HTTPException(status_code=500, detail="Failed to persist webhook payload.") from exc

        if media_asset_ids:
            background_tasks.add_task(process_media_downloads, media_asset_ids)

        # Queue agent processing for each inbound message
        for entry in payload.entry:
            for change in entry.changes:
                if change.field != "messages" or change.value is None:
                    continue
                for msg in change.value.messages:
                    if not msg.id or not msg.from_:
                        continue
                    contact_name = (
                        change.value.contacts[0].profile.name
                        if change.value.contacts
                        and change.value.contacts[0].profile
                        else None
                    )
                    text_body = msg.text.get("body") if msg.text else None
                    background_tasks.add_task(
                        process_with_agent,
                        sender_phone=msg.from_,
                        sender_name=contact_name,
                        message_id=msg.id,
                        message_text=text_body,
                        message_type=msg.type,
                    )

        return Response(status_code=200)

    @app.get("/api/messages")
    def list_messages(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        total = session.scalar(select(func.count(Message.id))) or 0
        messages = _fetch_messages(session=session, limit=limit, offset=offset)
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [_serialize_message(message) for message in messages],
        }

    @app.get("/messages", response_class=HTMLResponse)
    def view_messages(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        session: Session = Depends(get_session),
    ) -> HTMLResponse:
        total = session.scalar(select(func.count(Message.id))) or 0
        messages = _fetch_messages(session=session, limit=limit, offset=offset)
        return HTMLResponse(content=_render_messages_page(messages=messages, total=total, limit=limit, offset=offset))

    @app.post("/api/media/retry")
    def retry_media_downloads(
        background_tasks: BackgroundTasks,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, object]:
        media_asset_ids = get_retryable_media_asset_ids(limit=limit)
        if media_asset_ids:
            background_tasks.add_task(process_media_downloads, media_asset_ids)
        return {"queued": len(media_asset_ids), "media_asset_ids": media_asset_ids}

    return app


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _fetch_messages(session: Session, limit: int, offset: int) -> list[Message]:
    statement = (
        select(Message)
        .options(joinedload(Message.media_assets))
        .order_by(Message.whatsapp_timestamp.desc().nullslast(), Message.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return session.scalars(statement).unique().all()


def _serialize_message(message: Message) -> dict[str, object]:
    return {
        "id": message.id,
        "whatsapp_message_id": message.whatsapp_message_id,
        "direction": message.direction,
        "change_field": message.change_field,
        "message_type": message.message_type,
        "contact_name": message.contact_name,
        "wa_id": message.wa_id,
        "sender_wa_id": message.sender_wa_id,
        "recipient_wa_id": message.recipient_wa_id,
        "display_phone_number": message.display_phone_number,
        "phone_number_id": message.phone_number_id,
        "text_body": message.text_body,
        "caption": message.caption,
        "whatsapp_timestamp": message.whatsapp_timestamp.isoformat() if message.whatsapp_timestamp else None,
        "created_at": message.created_at.isoformat(),
        "media_assets": [_serialize_media_asset(media_asset) for media_asset in message.media_assets],
    }


def _serialize_media_asset(media_asset: MediaAsset) -> dict[str, object]:
    media_url = f"/media/{quote(media_asset.storage_path, safe='/')}" if media_asset.storage_path else None
    return {
        "id": media_asset.id,
        "media_type": media_asset.media_type,
        "whatsapp_media_id": media_asset.whatsapp_media_id,
        "mime_type": media_asset.mime_type,
        "download_status": media_asset.download_status,
        "storage_path": media_asset.storage_path,
        "media_url": media_url,
        "error_text": media_asset.error_text,
    }


def _render_messages_page(messages: list[Message], total: int, limit: int, offset: int) -> str:
    cards = "\n".join(_render_message_card(message) for message in messages) or "<p>No messages stored yet.</p>"
    next_offset = offset + limit
    previous_offset = max(offset - limit, 0)
    previous_link = (
        f'<a class="nav-link" href="/messages?limit={limit}&offset={previous_offset}">Previous</a>'
        if offset > 0
        else '<span class="nav-link disabled">Previous</span>'
    )
    next_link = (
        f'<a class="nav-link" href="/messages?limit={limit}&offset={next_offset}">Next</a>'
        if next_offset < total
        else '<span class="nav-link disabled">Next</span>'
    )
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>WhatsApp Messages</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f4f7fb;
        --card: #ffffff;
        --line: #d8e0ec;
        --text: #172033;
        --muted: #5e6a82;
        --accent: #0a7c66;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: linear-gradient(180deg, #eef6f2 0%, var(--bg) 40%);
        color: var(--text);
      }}
      main {{
        max-width: 980px;
        margin: 0 auto;
        padding: 32px 20px 48px;
      }}
      .header {{
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: end;
        margin-bottom: 24px;
        flex-wrap: wrap;
      }}
      .summary {{
        color: var(--muted);
        font-size: 14px;
      }}
      .nav {{
        display: flex;
        gap: 10px;
        align-items: center;
      }}
      .nav-link {{
        padding: 10px 14px;
        border-radius: 999px;
        text-decoration: none;
        border: 1px solid var(--line);
        background: var(--card);
        color: var(--text);
      }}
      .disabled {{
        opacity: 0.45;
      }}
      .message-list {{
        display: grid;
        gap: 16px;
      }}
      .card {{
        background: var(--card);
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 18px;
        box-shadow: 0 10px 30px rgba(23, 32, 51, 0.06);
      }}
      .card-top {{
        display: flex;
        justify-content: space-between;
        gap: 12px;
        flex-wrap: wrap;
        margin-bottom: 12px;
      }}
      .pill {{
        display: inline-block;
        padding: 5px 10px;
        border-radius: 999px;
        background: rgba(10, 124, 102, 0.1);
        color: var(--accent);
        font-size: 12px;
        font-weight: 600;
      }}
      .meta {{
        color: var(--muted);
        font-size: 13px;
      }}
      .content {{
        white-space: pre-wrap;
        margin: 12px 0;
        line-height: 1.5;
      }}
      .label {{
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
      }}
      .media-grid {{
        display: grid;
        gap: 12px;
        margin-top: 14px;
      }}
      .media-card {{
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 12px;
        background: #fbfcfe;
      }}
      img {{
        display: block;
        max-width: 100%;
        border-radius: 12px;
        margin-top: 10px;
      }}
      code {{
        font-size: 12px;
        word-break: break-all;
      }}
      a.inline-link {{
        color: var(--accent);
      }}
    </style>
  </head>
  <body>
    <main>
      <section class="header">
        <div>
          <h1>Stored WhatsApp messages</h1>
          <div class="summary">Showing {len(messages)} of {total} stored messages.</div>
        </div>
        <div class="nav">
          <a class="nav-link" href="/api/messages?limit={limit}&offset={offset}">View JSON</a>
          {previous_link}
          {next_link}
        </div>
      </section>
      <section class="message-list">
        {cards}
      </section>
    </main>
  </body>
</html>"""


def _render_message_card(message: Message) -> str:
    text_parts = [part for part in [message.text_body, message.caption] if part]
    content = "\n\n".join(text_parts) if text_parts else "No text body stored."
    media_html = "\n".join(_render_media_card(media_asset) for media_asset in message.media_assets)
    timestamp = message.whatsapp_timestamp.isoformat() if message.whatsapp_timestamp else message.created_at.isoformat()
    who = escape(message.contact_name or message.wa_id or message.sender_wa_id or "Unknown contact")
    message_type = escape(message.message_type or "unknown")
    direction = escape(message.direction)
    message_id = escape(message.whatsapp_message_id)
    return f"""
    <article class="card">
      <div class="card-top">
        <div>
          <span class="pill">{direction}</span>
          <div><strong>{who}</strong></div>
          <div class="meta">{message_type} • {escape(timestamp)}</div>
        </div>
        <div class="meta"><span class="label">Message ID</span><br /><code>{message_id}</code></div>
      </div>
      <div class="content">{escape(content)}</div>
      {f'<div class="media-grid">{media_html}</div>' if media_html else ''}
    </article>"""


def _render_media_card(media_asset: MediaAsset) -> str:
    media = _serialize_media_asset(media_asset)
    media_url = media["media_url"]
    error_text = escape(media_asset.error_text or "")
    preview = ""
    if media_url and media_asset.media_type == "image" and media_asset.download_status == "downloaded":
        preview = f'<a class="inline-link" href="{media_url}" target="_blank">Open image</a><img src="{media_url}" alt="WhatsApp image" loading="lazy" />'
    elif media_url:
        preview = f'<a class="inline-link" href="{media_url}" target="_blank">Open file</a>'
    return f"""
      <div class="media-card">
        <div class="label">Media</div>
        <div class="meta">{escape(media_asset.media_type)} • {escape(media_asset.download_status)}</div>
        {f'<div class="meta">{error_text}</div>' if error_text else ''}
        {preview}
      </div>"""


app = create_app()
