from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from whatsapp_automation.config import get_settings
from whatsapp_automation.db import configure_engine, reset_engine

POSTGRES_BIN_DIR = Path("/opt/homebrew/opt/postgresql@15/bin")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_database(database_url: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            engine = create_engine(database_url)
            with engine.connect():
                return
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
        finally:
            if "engine" in locals():
                engine.dispose()
    raise RuntimeError("Temporary PostgreSQL server did not become ready in time.")


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    base_dir = tmp_path_factory.mktemp("postgres")
    data_dir = base_dir / "data"
    log_file = base_dir / "postgres.log"
    port = _find_free_port()

    env = {**os.environ, "LC_ALL": "C"}
    subprocess.run(
        [
            str(POSTGRES_BIN_DIR / "initdb"),
            "-D",
            str(data_dir),
            "-A",
            "trust",
            "-U",
            "postgres",
            "--encoding=UTF8",
            "--no-locale",
        ],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    with (data_dir / "postgresql.conf").open("a", encoding="utf-8") as config_file:
        config_file.write(
            f"\nlisten_addresses = '127.0.0.1'\n"
            f"port = {port}\n"
            "unix_socket_directories = '/tmp'\n"
            "fsync = off\n"
            "synchronous_commit = off\n"
            "full_page_writes = off\n"
        )

    subprocess.run(
        [
            str(POSTGRES_BIN_DIR / "pg_ctl"),
            "-D",
            str(data_dir),
            "-l",
            str(log_file),
            "start",
        ],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    url = f"postgresql+psycopg://postgres@127.0.0.1:{port}/postgres"
    _wait_for_database(url)

    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", url)
    command.upgrade(alembic_config, "head")

    try:
        yield url
    finally:
        subprocess.run(
            [
                str(POSTGRES_BIN_DIR / "pg_ctl"),
                "-D",
                str(data_dir),
                "-m",
                "immediate",
                "stop",
            ],
            check=True,
            env=env,
            capture_output=True,
            text=True,
        )


@pytest.fixture(autouse=True)
def clean_database(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE portfolio_transactions, portfolio_holdings, media_assets, messages, webhook_events RESTART IDENTITY CASCADE"))
    engine.dispose()


@pytest.fixture
def client(database_url: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "kapil")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("WHATSAPP_GRAPH_API_VERSION", "v23.0")
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path / "media"))
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    get_settings.cache_clear()
    reset_engine()
    configure_engine(database_url)

    from fastapi.testclient import TestClient
    from whatsapp_automation.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client

    reset_engine()
    get_settings.cache_clear()
