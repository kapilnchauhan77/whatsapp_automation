from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = Field(default=3000, alias="PORT")
    whatsapp_verify_token: str = Field(default="kapil", alias="WHATSAPP_VERIFY_TOKEN")
    whatsapp_access_token: str | None = Field(default=None, alias="WHATSAPP_ACCESS_TOKEN")
    whatsapp_phone_number_id: str | None = Field(default=None, alias="WHATSAPP_PHONE_NUMBER_ID")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/whatsapp_automation",
        alias="DATABASE_URL",
    )
    media_storage_root: Path = Field(default=Path("./storage/media"), alias="MEDIA_STORAGE_ROOT")
    whatsapp_graph_api_version: str = Field(default="v23.0", alias="WHATSAPP_GRAPH_API_VERSION")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        # Railway/Render use "postgresql://" but psycopg requires "postgresql+psycopg://"
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("media_storage_root", mode="before")
    @classmethod
    def expand_media_storage_root(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
