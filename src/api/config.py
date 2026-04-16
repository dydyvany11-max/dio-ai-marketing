from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILES = (
    PROJECT_ROOT / ".env",
    PROJECT_ROOT / ".venv" / ".env",
)


@dataclass(frozen=True)
class VKSettings:
    app_id: int
    app_secret: str
    redirect_uri: str
    api_version: str


@dataclass(frozen=True)
class VKIDSettings:
    app_id: int
    redirect_uri: str
    domain: str
    scope: str


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


@dataclass(frozen=True)
class YandexGPTSettings:
    api_key: str | None
    iam_token: str | None
    model_uri: str
    base_url: str
    timeout_sec: int


@dataclass(frozen=True)
class AIUsagePricingSettings:
    currency: str
    gigachat_input_per_1k: float
    gigachat_output_per_1k: float
    yandex_input_per_1k: float
    yandex_output_per_1k: float

    def rates_for(self, provider: str) -> tuple[float, float]:
        normalized = str(provider or "").strip().lower()
        if normalized == "gigachat":
            return self.gigachat_input_per_1k, self.gigachat_output_per_1k
        if normalized == "yandex":
            return self.yandex_input_per_1k, self.yandex_output_per_1k
        return 0.0, 0.0


@dataclass(frozen=True)
class TrendsSettings:
    db_path: str
    window_hours: int
    max_terms: int
    newsapi_key: str | None
    newsapi_sources: list[str]
    gdelt_query: str | None


def _load_project_env() -> None:
    for env_path in DEFAULT_ENV_FILES:
        if env_path.exists():
            load_dotenv(env_path, override=False)


def is_gigachat_configured() -> bool:
    _load_project_env()
    return bool(
        os.getenv("GIGACHAT_CREDENTIALS", "").strip()
        or os.getenv("GIGACHAT_AUTH_KEY", "").strip()
        or os.getenv("GIGACHAT_AUTHORIZATION_KEY", "").strip()
        or os.getenv("GIGACHAT_ACCESS_TOKEN", "").strip()
    )


def is_yandexgpt_configured() -> bool:
    _load_project_env()
    has_auth = bool(
        os.getenv("YANDEX_GPT_API_KEY", "").strip()
        or os.getenv("YANDEX_CLOUD_API_KEY", "").strip()
        or os.getenv("YANDEX_GPT_IAM_TOKEN", "").strip()
    )
    has_model = bool(
        os.getenv("YANDEX_GPT_MODEL_URI", "").strip()
        or os.getenv("YANDEX_CLOUD_FOLDER_ID", "").strip()
    )
    return has_auth and has_model


def is_vk_configured() -> bool:
    _load_project_env()
    app_id_raw = os.getenv("VK_APP_ID", "").strip()
    app_secret = os.getenv("VK_APP_SECRET", "").strip()
    redirect_uri = os.getenv("VK_REDIRECT_URI", "").strip()

    try:
        app_id = int(app_id_raw)
    except (TypeError, ValueError):
        return False

    return app_id > 0 and bool(app_secret) and bool(redirect_uri)


def is_vkid_configured() -> bool:
    _load_project_env()
    app_id_raw = os.getenv("VKID_APP_ID", "").strip() or os.getenv("VK_APP_ID", "").strip()
    redirect_uri = os.getenv("VKID_REDIRECT_URI", "").strip() or os.getenv("VK_REDIRECT_URI", "").strip()

    try:
        app_id = int(app_id_raw)
    except (TypeError, ValueError):
        return False

    return app_id > 0 and bool(redirect_uri)


def load_vk_settings() -> VKSettings:
    _load_project_env()

    app_id_raw = os.getenv("VK_APP_ID", "0").strip()
    app_secret = os.getenv("VK_APP_SECRET", "").strip()
    redirect_uri = os.getenv("VK_REDIRECT_URI", "").strip()
    api_version = os.getenv("VK_API_VERSION", "5.199").strip() or "5.199"

    try:
        app_id = int(app_id_raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Set VK_APP_ID in .env") from exc

    if not app_id or not app_secret or not redirect_uri:
        raise RuntimeError("Set VK_APP_ID, VK_APP_SECRET, VK_REDIRECT_URI in .env")

    return VKSettings(
        app_id=app_id,
        app_secret=app_secret,
        redirect_uri=redirect_uri,
        api_version=api_version,
    )


def load_vk_api_settings() -> VKSettings:
    _load_project_env()

    app_id_raw = os.getenv("VK_APP_ID", "").strip() or os.getenv("VKID_APP_ID", "").strip()
    api_version = os.getenv("VK_API_VERSION", "5.199").strip() or "5.199"

    try:
        app_id = int(app_id_raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Set VK_APP_ID (or VKID_APP_ID) in .env") from exc

    if not app_id:
        raise RuntimeError("Set VK_APP_ID (or VKID_APP_ID) in .env")

    return VKSettings(
        app_id=app_id,
        app_secret="",
        redirect_uri="",
        api_version=api_version,
    )


def load_vkid_settings() -> VKIDSettings:
    _load_project_env()

    app_id_raw = os.getenv("VKID_APP_ID", "").strip() or os.getenv("VK_APP_ID", "0").strip()
    redirect_uri = os.getenv("VKID_REDIRECT_URI", "").strip() or os.getenv("VK_REDIRECT_URI", "").strip()
    domain = os.getenv("VKID_DOMAIN", "id.vk.ru").strip() or "id.vk.ru"
    scope = os.getenv("VKID_SCOPE", "vkid.personal_info").strip() or "vkid.personal_info"

    try:
        app_id = int(app_id_raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Set VKID_APP_ID (or VK_APP_ID) in .env") from exc

    if not app_id or not redirect_uri:
        raise RuntimeError("Set VKID_APP_ID (or VK_APP_ID) and VKID_REDIRECT_URI (or VK_REDIRECT_URI) in .env")

    return VKIDSettings(
        app_id=app_id,
        redirect_uri=redirect_uri,
        domain=domain,
        scope=scope,
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


def load_yandexgpt_settings() -> YandexGPTSettings:
    _load_project_env()

    api_key = (
        os.getenv("YANDEX_GPT_API_KEY", "").strip()
        or os.getenv("YANDEX_CLOUD_API_KEY", "").strip()
        or None
    )
    iam_token = os.getenv("YANDEX_GPT_IAM_TOKEN", "").strip() or None
    folder_id = os.getenv("YANDEX_CLOUD_FOLDER_ID", "").strip()
    model_name = os.getenv("YANDEX_GPT_MODEL_NAME", "yandexgpt-5-lite").strip() or "yandexgpt-5-lite"
    model_uri = os.getenv("YANDEX_GPT_MODEL_URI", "").strip() or ""
    if not model_uri and folder_id:
        model_uri = f"gpt://{folder_id}/{model_name}"
    base_url = (
        os.getenv("YANDEX_GPT_BASE_URL", "https://llm.api.cloud.yandex.net/foundationModels/v1/completion").strip()
        or "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    )
    timeout_raw = os.getenv("YANDEX_GPT_TIMEOUT_SEC", "60").strip()
    try:
        timeout_sec = max(10, int(timeout_raw))
    except ValueError:
        timeout_sec = 60

    if not (api_key or iam_token):
        raise RuntimeError(
            "Set YANDEX_GPT_API_KEY (or YANDEX_CLOUD_API_KEY) or YANDEX_GPT_IAM_TOKEN in .env"
        )
    if not model_uri:
        raise RuntimeError(
            "Set YANDEX_GPT_MODEL_URI in .env or YANDEX_CLOUD_FOLDER_ID to auto-build model URI"
        )

    return YandexGPTSettings(
        api_key=api_key,
        iam_token=iam_token,
        model_uri=model_uri,
        base_url=base_url,
        timeout_sec=timeout_sec,
    )


def load_ai_usage_pricing_settings() -> AIUsagePricingSettings:
    _load_project_env()

    def _float_from_env(name: str, default: float) -> float:
        raw = os.getenv(name, "").strip()
        if not raw:
            return float(default)
        try:
            return max(0.0, float(raw))
        except ValueError:
            return float(default)

    currency = os.getenv("AI_USAGE_CURRENCY", "RUB").strip().upper() or "RUB"
    return AIUsagePricingSettings(
        currency=currency,
        gigachat_input_per_1k=_float_from_env("GIGACHAT_PRICE_INPUT_PER_1K", 0.0),
        gigachat_output_per_1k=_float_from_env("GIGACHAT_PRICE_OUTPUT_PER_1K", 0.0),
        yandex_input_per_1k=_float_from_env("YANDEX_GPT_PRICE_INPUT_PER_1K", 0.0),
        yandex_output_per_1k=_float_from_env("YANDEX_GPT_PRICE_OUTPUT_PER_1K", 0.0),
    )


def load_trends_settings() -> TrendsSettings:
    _load_project_env()

    db_path = os.getenv("TRENDS_DB_PATH", str((PROJECT_ROOT / "db" / "trends.db").resolve()))
    window_hours = int(os.getenv("TRENDS_WINDOW_HOURS", "6"))
    max_terms = int(os.getenv("TRENDS_MAX_TERMS", "50"))
    newsapi_key = os.getenv("NEWSAPI_KEY", "").strip() or None
    newsapi_sources = [
        s.strip() for s in os.getenv("NEWSAPI_SOURCES", "").split(",") if s.strip()
    ]
    gdelt_query = os.getenv("GDELT_QUERY", "").strip() or None

    return TrendsSettings(
        db_path=db_path,
        window_hours=window_hours,
        max_terms=max_terms,
        newsapi_key=newsapi_key,
        newsapi_sources=newsapi_sources,
        gdelt_query=gdelt_query,
    )
