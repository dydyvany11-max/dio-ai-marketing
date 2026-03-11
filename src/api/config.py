from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILES = (
    PROJECT_ROOT / ".env",
    PROJECT_ROOT / ".venv" / ".env",
)


@dataclass(frozen=True)
class TelegramSettings:
    api_id: int
    api_hash: str
    session_path: str


@dataclass(frozen=True)
class GigaChatSettings:
    credentials: str | None
    authorization_key: str | None
    client_id: str | None
    model: str
    verify_ssl_certs: bool
    scope: str
    auth_url: str
    base_url: str


def _load_project_env() -> None:
    for env_path in DEFAULT_ENV_FILES:
        if env_path.exists():
            load_dotenv(env_path, override=False)


def is_telegram_configured() -> bool:
    _load_project_env()
    api_id_raw = os.getenv("TG_API_ID", "").strip()
    api_hash = os.getenv("TG_API_HASH", "").strip()

    try:
        api_id = int(api_id_raw)
    except (TypeError, ValueError):
        return False

    return api_id > 0 and bool(api_hash)


def is_gigachat_configured() -> bool:
    _load_project_env()
    return bool(
        os.getenv("GIGACHAT_CREDENTIALS", "").strip()
        or os.getenv("GIGACHAT_AUTH_KEY", "").strip()
        or os.getenv("GIGACHAT_AUTHORIZATION_KEY", "").strip()
        or os.getenv("GIGACHAT_ACCESS_TOKEN", "").strip()
    )


def load_settings() -> TelegramSettings:
    _load_project_env()

    api_id = int(os.getenv("TG_API_ID", "0"))
    api_hash = os.getenv("TG_API_HASH", "")
    session_name = os.getenv("TG_SESSION_NAME", "tg_session")

    if not api_id or not api_hash:
        raise RuntimeError("Set TG_API_ID and TG_API_HASH in .env")

    session_path = str((PROJECT_ROOT / session_name).resolve())
    return TelegramSettings(
        api_id=api_id,
        api_hash=api_hash,
        session_path=session_path,
    )


def load_gigachat_settings() -> GigaChatSettings:
    _load_project_env()

    credentials = os.getenv("GIGACHAT_CREDENTIALS", "").strip() or None
    authorization_key = (
        os.getenv("GIGACHAT_AUTH_KEY", "").strip()
        or os.getenv("GIGACHAT_AUTHORIZATION_KEY", "").strip()
        or os.getenv("GIGACHAT_ACCESS_TOKEN", "").strip()
        or None
    )
    client_id = os.getenv("GIGACHAT_CLIENT_ID", "").strip() or None
    model = os.getenv("GIGACHAT_MODEL", "GigaChat-2-Max").strip() or "GigaChat-2-Max"
    scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip() or "GIGACHAT_API_PERS"
    auth_url = (
        os.getenv("GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth").strip()
        or "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    )
    base_url = (
        os.getenv("GIGACHAT_BASE_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions").strip()
        or "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    )
    verify_ssl_raw = os.getenv("GIGACHAT_VERIFY_SSL_CERTS", "false").strip().lower()
    verify_ssl_certs = verify_ssl_raw in {"1", "true", "yes", "on"}

    if not authorization_key and not credentials:
        raise RuntimeError(
            "Set GIGACHAT_AUTH_KEY or GIGACHAT_AUTHORIZATION_KEY in .env"
        )

    if authorization_key:
        authorization_key = authorization_key.lstrip("=")

    return GigaChatSettings(
        credentials=credentials,
        authorization_key=authorization_key,
        client_id=client_id,
        model=model,
        verify_ssl_certs=verify_ssl_certs,
        scope=scope,
        auth_url=auth_url,
        base_url=base_url,
    )
