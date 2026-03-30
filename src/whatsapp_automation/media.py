from __future__ import annotations

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from whatsapp_automation.config import get_settings
from whatsapp_automation.db import get_session_factory
from whatsapp_automation.models import MediaAsset, Message


def process_media_downloads(media_asset_ids: list[int]) -> None:
    for media_asset_id in media_asset_ids:
        _download_media_asset(media_asset_id)


def get_retryable_media_asset_ids(limit: int = 100) -> list[int]:
    session_factory = get_session_factory()
    with session_factory() as session:
        media_assets = session.scalars(
            select(MediaAsset)
            .order_by(MediaAsset.created_at.asc())
            .limit(limit * 3)
        ).all()

    settings = get_settings()
    retryable_ids: list[int] = []
    for media_asset in media_assets:
        if _media_asset_needs_download(media_asset=media_asset, media_root=settings.media_storage_root):
            retryable_ids.append(media_asset.id)
        if len(retryable_ids) >= limit:
            break
    return retryable_ids


def _download_media_asset(media_asset_id: int) -> None:
    settings = get_settings()
    if not settings.whatsapp_access_token:
        _mark_media_failure(media_asset_id, "WHATSAPP_ACCESS_TOKEN is not configured.")
        return

    session_factory = get_session_factory()
    try:
        with session_factory() as session:
            media_asset = session.scalar(
                select(MediaAsset)
                .options(joinedload(MediaAsset.message).joinedload(Message.webhook_event))
                .where(MediaAsset.id == media_asset_id)
            )
            if media_asset is None:
                return
            if not _media_asset_needs_download(media_asset=media_asset, media_root=settings.media_storage_root):
                return

            media_url, metadata, content, content_type = _resolve_download_target(
                media_asset=media_asset,
                access_token=settings.whatsapp_access_token,
            )
            media_asset.mime_type = content_type or metadata.get("mime_type") or media_asset.mime_type
            media_asset.sha256 = metadata.get("sha256") or media_asset.sha256
            media_asset.source_url = media_url

            destination = _build_media_path(media_asset=media_asset, media_root=settings.media_storage_root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)

            media_asset.storage_path = str(destination.relative_to(settings.media_storage_root))
            media_asset.download_status = "downloaded"
            media_asset.downloaded_at = datetime.now(timezone.utc)
            media_asset.error_text = None
            session.commit()
    except Exception as exc:  # noqa: BLE001
        _mark_media_failure(media_asset_id, str(exc))


def _resolve_download_target(
    media_asset: MediaAsset,
    access_token: str,
) -> tuple[str, dict[str, Any], bytes, str | None]:
    attempts: list[str] = []
    settings = get_settings()

    if media_asset.source_url:
        try:
            content, content_type = _download_media_bytes(media_asset.source_url, access_token)
            return media_asset.source_url, {}, content, content_type
        except Exception as exc:  # noqa: BLE001
            attempts.append(str(exc))

    if not media_asset.whatsapp_media_id:
        raise RuntimeError("; ".join(attempts) or "No source URL or WhatsApp media id available.")

    metadata_url = f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/{media_asset.whatsapp_media_id}"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(metadata_url, headers=_authorization_headers(access_token))
        response.raise_for_status()
        payload = response.json()

    download_url = payload.get("url")
    if not isinstance(download_url, str) or not download_url:
        raise RuntimeError("Media metadata response did not include a download URL.")

    content, content_type = _download_media_bytes(download_url, access_token)
    return download_url, payload, content, content_type


def _download_media_bytes(url: str, access_token: str) -> tuple[bytes, str | None]:
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        response = client.get(url, headers=_authorization_headers(access_token))
        response.raise_for_status()
        content_type = response.headers.get("content-type")
        if content_type:
            content_type = content_type.split(";", maxsplit=1)[0].strip()
        return response.content, content_type


def _authorization_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _build_media_path(media_asset: MediaAsset, media_root: Path) -> Path:
    message = media_asset.message
    event_date = (
        message.whatsapp_timestamp
        or (message.webhook_event.received_at if message.webhook_event else None)
        or datetime.now(timezone.utc)
    )
    extension = _extension_for_mime_type(media_asset.mime_type)
    phone_number_id = message.phone_number_id or "unknown_phone_number"
    filename = f"{message.whatsapp_message_id}{extension}"
    return (
        media_root
        / phone_number_id
        / event_date.strftime("%Y")
        / event_date.strftime("%m")
        / event_date.strftime("%d")
        / filename
    )


def _extension_for_mime_type(mime_type: str | None) -> str:
    if not mime_type:
        return ".bin"
    if mime_type == "image/jpeg":
        return ".jpg"
    return mimetypes.guess_extension(mime_type) or ".bin"


def _media_asset_needs_download(media_asset: MediaAsset, media_root: Path) -> bool:
    if media_asset.download_status != "downloaded":
        return True
    if not media_asset.storage_path:
        return True
    return not (media_root / media_asset.storage_path).exists()


def _mark_media_failure(media_asset_id: int, error_text: str) -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        media_asset = session.get(MediaAsset, media_asset_id)
        if media_asset is None:
            return
        media_asset.download_status = "failed"
        media_asset.error_text = error_text[:2000]
        session.commit()
