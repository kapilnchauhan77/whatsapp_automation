from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from whatsapp_automation.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_configured_url: str | None = None


def configure_engine(database_url: str | None = None) -> Engine:
    global _engine, _session_factory, _configured_url

    target_url = database_url or get_settings().database_url
    if _engine is not None and _configured_url == target_url:
        return _engine

    if _engine is not None:
        _engine.dispose()

    _engine = create_engine(target_url, pool_pre_ping=True)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    _configured_url = target_url
    return _engine


def reset_engine() -> None:
    global _engine, _session_factory, _configured_url

    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _configured_url = None


def get_engine() -> Engine:
    return configure_engine()


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        configure_engine()
    assert _session_factory is not None
    return _session_factory


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
