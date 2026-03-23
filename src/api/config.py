from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILES = tuple(
    str(path)
    for path in (
        PROJECT_ROOT / ".env",
        PROJECT_ROOT / ".venv" / ".env",
    )
    if path.exists()
)


class _BaseProjectSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILES or None,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class TelegramSettings(_BaseProjectSettings):
    api_id: int = Field(default=0, alias="TG_API_ID")
    api_hash: str = Field(default="", alias="TG_API_HASH")
    session_name: str = Field(default="tg_session", alias="TG_SESSION_NAME")

    @property
    def session_path(self) -> str:
        return str((PROJECT_ROOT / self.session_name).resolve())


class GigaChatSettings(_BaseProjectSettings):
    credentials: str | None = Field(default=None, alias="GIGACHAT_CREDENTIALS")
    authorization_key: str | None = Field(default=None, alias="GIGACHAT_AUTH_KEY")
    authorization_key_alt: str | None = Field(default=None, alias="GIGACHAT_AUTHORIZATION_KEY")
    access_token: str | None = Field(default=None, alias="GIGACHAT_ACCESS_TOKEN")
    client_id: str | None = Field(default=None, alias="GIGACHAT_CLIENT_ID")
    model: str = Field(default="GigaChat-2-Max", alias="GIGACHAT_MODEL")
    scope: str = Field(default="GIGACHAT_API_PERS", alias="GIGACHAT_SCOPE")
    auth_url: str = Field(
        default="https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        alias="GIGACHAT_AUTH_URL",
    )
    base_url: str = Field(
        default="https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
        alias="GIGACHAT_BASE_URL",
    )
    verify_ssl_certs: bool = Field(default=False, alias="GIGACHAT_VERIFY_SSL_CERTS")

    @property
    def resolved_credentials(self) -> str | None:
        return (
            self.credentials
            or self.authorization_key
            or self.authorization_key_alt
            or self.access_token
        )

    @property
    def normalized_base_url(self) -> str:
        base_url = (self.base_url or "").rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url[: -len("/chat/completions")]
        return base_url


class AppSettings(_BaseProjectSettings):
    host: str = Field(default="127.0.0.1", alias="API_HOST")
    port: int = Field(default=8000, alias="API_PORT", ge=1, le=65535)
    reload: bool = Field(default=False, alias="API_RELOAD")


class StorageSettings(_BaseProjectSettings):
    sqlite_db_path: Path = Field(
        default_factory=lambda: PROJECT_ROOT / "db" / "channels.db",
        alias="SQLITE_DB_PATH",
    )

    @property
    def resolved_sqlite_db_path(self) -> Path:
        if self.sqlite_db_path.is_absolute():
            return self.sqlite_db_path
        return (PROJECT_ROOT / self.sqlite_db_path).resolve()


class AnalysisSettings(_BaseProjectSettings):
    competitor_search_limit_per_query: int = Field(
        default=8,
        alias="ANALYSIS_COMPETITOR_SEARCH_LIMIT_PER_QUERY",
        ge=1,
        le=50,
    )
    ai_keyword_message_limit: int = Field(
        default=12,
        alias="ANALYSIS_AI_KEYWORD_MESSAGE_LIMIT",
        ge=1,
        le=100,
    )
    ai_keyword_batch_size: int = Field(
        default=6,
        alias="ANALYSIS_AI_KEYWORD_BATCH_SIZE",
        ge=1,
        le=20,
    )
    ai_keyword_text_limit: int = Field(
        default=120,
        alias="ANALYSIS_AI_KEYWORD_TEXT_LIMIT",
        ge=20,
        le=2000,
    )


@lru_cache(maxsize=1)
def get_telegram_settings() -> TelegramSettings:
    return TelegramSettings()


@lru_cache(maxsize=1)
def get_gigachat_settings() -> GigaChatSettings:
    return GigaChatSettings()


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    return AppSettings()


@lru_cache(maxsize=1)
def get_storage_settings() -> StorageSettings:
    return StorageSettings()


@lru_cache(maxsize=1)
def get_analysis_settings() -> AnalysisSettings:
    return AnalysisSettings()


def is_telegram_configured() -> bool:
    settings = get_telegram_settings()
    return settings.api_id > 0 and bool(settings.api_hash.strip())


def is_gigachat_configured() -> bool:
    settings = get_gigachat_settings()
    return bool(settings.resolved_credentials)


def load_settings() -> TelegramSettings:
    settings = get_telegram_settings()
    if not settings.api_id or not settings.api_hash:
        raise RuntimeError("Set TG_API_ID and TG_API_HASH in .env")
    return settings


def load_gigachat_settings() -> GigaChatSettings:
    settings = get_gigachat_settings()
    if not settings.resolved_credentials:
        raise RuntimeError("Set GIGACHAT_AUTH_KEY or GIGACHAT_CREDENTIALS in .env")
    return settings
