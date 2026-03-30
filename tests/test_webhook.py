from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session

from whatsapp_automation.models import MediaAsset, Message, WebhookEvent


TEXT_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "4202086610044709",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "917436037984",
                            "phone_number_id": "1053075394553252",
                        },
                        "contacts": [
                            {
                                "profile": {
                                    "name": "Kapil Chauhan",
                                },
                                "wa_id": "917984147792",
                            }
                        ],
                        "messages": [
                            {
                                "from": "917984147792",
                                "id": "wamid.text.1",
                                "timestamp": "1773142880",
                                "text": {
                                    "body": "How are you",
                                },
                                "type": "text",
                            }
                        ],
                    },
                }
            ],
        }
    ],
}

ECHO_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "0",
            "changes": [
                {
                    "field": "message_echoes",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "16505551111",
                            "phone_number_id": "123456123",
                        },
                        "message_echoes": [
                            {
                                "from": "16505551111",
                                "to": "16315551181",
                                "id": "wamid.echo.1",
                                "timestamp": "1773142900",
                                "type": "text",
                                "message_creation_type": "created_by_1p_bot",
                                "text": {
                                    "body": "this is a text message",
                                },
                            }
                        ],
                    },
                }
            ],
        }
    ],
}

IMAGE_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "4202086610044709",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "917436037984",
                            "phone_number_id": "1053075394553252",
                        },
                        "contacts": [
                            {
                                "profile": {
                                    "name": "Kapil Chauhan",
                                },
                                "wa_id": "917984147792",
                            }
                        ],
                        "messages": [
                            {
                                "from": "917984147792",
                                "id": "wamid.image.1",
                                "timestamp": "1773142956",
                                "type": "image",
                                "image": {
                                    "caption": "02/03/2026\nYellow capsicum 3.5 kg \n150 rs",
                                    "mime_type": "image/jpeg",
                                    "sha256": "sha-value",
                                    "id": "4253653188282881",
                                    "url": "https://lookaside.example/media/4253653188282881",
                                },
                            }
                        ],
                    },
                }
            ],
        }
    ],
}


class FakeResponse:
    def __init__(self, *, status_code: int = 200, json_data=None, content: bytes = b"", headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


class FakeHttpxClient:
    def __init__(self, responses):
        self.responses = responses

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):  # noqa: ANN001
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


def test_verify_webhook_success(client) -> None:
    response = client.get(
        "/",
        params={"hub.mode": "subscribe", "hub.challenge": "12345", "hub.verify_token": "kapil"},
    )

    assert response.status_code == 200
    assert response.text == "12345"


def test_verify_webhook_failure(client) -> None:
    response = client.get(
        "/",
        params={"hub.mode": "subscribe", "hub.challenge": "12345", "hub.verify_token": "wrong"},
    )

    assert response.status_code == 403


def test_inbound_text_payload_persists_event_and_message(client, database_url: str) -> None:
    response = client.post("/", json=TEXT_PAYLOAD)
    assert response.status_code == 200

    engine = create_engine(database_url)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WebhookEvent)) == 1
        assert session.scalar(select(func.count()).select_from(Message)) == 1

        message = session.scalar(select(Message).where(Message.whatsapp_message_id == "wamid.text.1"))
        assert message is not None
        assert message.direction == "inbound"
        assert message.text_body == "How are you"
        assert message.wa_id == "917984147792"
    engine.dispose()


def test_message_echoes_payload_persists_outbound_message(client, database_url: str) -> None:
    response = client.post("/", json=ECHO_PAYLOAD)
    assert response.status_code == 200

    engine = create_engine(database_url)
    with Session(engine) as session:
        message = session.scalar(select(Message).where(Message.whatsapp_message_id == "wamid.echo.1"))
        assert message is not None
        assert message.direction == "outbound_echo"
        assert message.change_field == "message_echoes"
        assert message.wa_id == "16315551181"
    engine.dispose()


def test_image_payload_downloads_and_saves_file(client, database_url: str, monkeypatch, tmp_path: Path) -> None:
    from whatsapp_automation import media

    responses = {
        "https://lookaside.example/media/4253653188282881": FakeResponse(
            content=b"image-bytes",
            headers={"content-type": "image/jpeg"},
        )
    }
    monkeypatch.setattr(media.httpx, "Client", lambda *args, **kwargs: FakeHttpxClient(responses))

    response = client.post("/", json=IMAGE_PAYLOAD)
    assert response.status_code == 200

    engine = create_engine(database_url)
    with Session(engine) as session:
        media_asset = session.scalar(select(MediaAsset).where(MediaAsset.whatsapp_media_id == "4253653188282881"))
        assert media_asset is not None
        assert media_asset.download_status == "downloaded"
        assert media_asset.storage_path is not None
        saved_file = tmp_path / "media" / media_asset.storage_path
        assert saved_file.exists()
        assert saved_file.read_bytes() == b"image-bytes"
    engine.dispose()


def test_duplicate_webhook_does_not_duplicate_message_rows(client, database_url: str) -> None:
    first = client.post("/", json=TEXT_PAYLOAD)
    second = client.post("/", json=TEXT_PAYLOAD)

    assert first.status_code == 200
    assert second.status_code == 200

    engine = create_engine(database_url)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(WebhookEvent)) == 2
        assert session.scalar(select(func.count()).select_from(Message)) == 1
    engine.dispose()


def test_media_download_failure_marks_asset_failed(client, database_url: str, monkeypatch) -> None:
    from whatsapp_automation import media

    responses = {
        "https://lookaside.example/media/4253653188282881": RuntimeError("lookaside expired"),
        "https://graph.facebook.com/v23.0/4253653188282881": FakeResponse(
            json_data={"url": "https://resolved.example/media/4253653188282881", "mime_type": "image/jpeg"},
        ),
        "https://resolved.example/media/4253653188282881": RuntimeError("resolved download failed"),
    }
    monkeypatch.setattr(media.httpx, "Client", lambda *args, **kwargs: FakeHttpxClient(responses))

    response = client.post("/", json=IMAGE_PAYLOAD)
    assert response.status_code == 200

    engine = create_engine(database_url)
    with Session(engine) as session:
        media_asset = session.scalar(select(MediaAsset).where(MediaAsset.whatsapp_media_id == "4253653188282881"))
        assert media_asset is not None
        assert media_asset.download_status == "failed"
        assert media_asset.error_text
    engine.dispose()


def test_messages_endpoints_show_text_and_images(client, monkeypatch) -> None:
    from whatsapp_automation import media

    responses = {
        "https://lookaside.example/media/4253653188282881": FakeResponse(
            content=b"image-bytes",
            headers={"content-type": "image/jpeg"},
        )
    }
    monkeypatch.setattr(media.httpx, "Client", lambda *args, **kwargs: FakeHttpxClient(responses))

    assert client.post("/", json=TEXT_PAYLOAD).status_code == 200
    assert client.post("/", json=IMAGE_PAYLOAD).status_code == 200

    html_response = client.get("/messages")
    assert html_response.status_code == 200
    assert "Stored WhatsApp messages" in html_response.text
    assert "How are you" in html_response.text
    assert "Open image" in html_response.text

    api_response = client.get("/api/messages")
    assert api_response.status_code == 200
    payload = api_response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2

    image_message = next(item for item in payload["items"] if item["whatsapp_message_id"] == "wamid.image.1")
    media_asset = image_message["media_assets"][0]
    assert media_asset["download_status"] == "downloaded"
    assert media_asset["media_url"].startswith("/media/")

    image_response = client.get(media_asset["media_url"])
    assert image_response.status_code == 200
    assert image_response.content == b"image-bytes"


def test_retry_endpoint_redownloads_failed_media(client, database_url: str, monkeypatch, tmp_path: Path) -> None:
    from whatsapp_automation import media

    failing_responses = {
        "https://lookaside.example/media/4253653188282881": RuntimeError("lookaside expired"),
        "https://graph.facebook.com/v23.0/4253653188282881": FakeResponse(
            json_data={"url": "https://resolved.example/media/4253653188282881", "mime_type": "image/jpeg"},
        ),
        "https://resolved.example/media/4253653188282881": RuntimeError("resolved download failed"),
    }
    monkeypatch.setattr(media.httpx, "Client", lambda *args, **kwargs: FakeHttpxClient(failing_responses))

    response = client.post("/", json=IMAGE_PAYLOAD)
    assert response.status_code == 200

    successful_responses = {
        "https://lookaside.example/media/4253653188282881": FakeResponse(
            content=b"retried-image-bytes",
            headers={"content-type": "image/jpeg"},
        )
    }
    monkeypatch.setattr(media.httpx, "Client", lambda *args, **kwargs: FakeHttpxClient(successful_responses))

    retry_response = client.post("/api/media/retry")
    assert retry_response.status_code == 200
    assert retry_response.json()["queued"] == 1

    engine = create_engine(database_url)
    with Session(engine) as session:
        media_asset = session.scalar(select(MediaAsset).where(MediaAsset.whatsapp_media_id == "4253653188282881"))
        assert media_asset is not None
        assert media_asset.download_status == "downloaded"
        assert media_asset.storage_path is not None
        saved_file = tmp_path / "media" / media_asset.storage_path
        assert saved_file.exists()
        assert saved_file.read_bytes() == b"retried-image-bytes"
    engine.dispose()


def test_alembic_schema_contains_expected_tables(database_url: str, client) -> None:
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {"webhook_events", "messages", "media_assets"}.issubset(set(inspector.get_table_names()))
    engine.dispose()
