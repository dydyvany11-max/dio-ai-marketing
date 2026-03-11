from functools import lru_cache
from typing import NamedTuple

from src.api.config import (
    is_gigachat_configured,
    load_gigachat_settings,
    load_settings,
)
from src.api.services.auth import TelegramAuthService
from src.api.services.audience import TelegramAudienceAnalyzer
from src.api.services.audience_ai import GigaChatAudienceEnhancer
from src.api.services.dto import GigaChatStatus
from src.api.services.interfaces import AuthServicePort, AudienceAnalyzerPort
from src.api.services.telegram_client import TelegramClientService


class _Services(NamedTuple):
    client_service: TelegramClientService
    auth_service: AuthServicePort
    audience_analyzer: AudienceAnalyzerPort


@lru_cache(maxsize=1)
def _build_services() -> _Services:
    settings = load_settings()
    client_service = TelegramClientService(settings)
    auth_service = TelegramAuthService(client_service)
    ai_enhancer = None
    if is_gigachat_configured():
        ai_enhancer = GigaChatAudienceEnhancer(load_gigachat_settings())
    audience_analyzer = TelegramAudienceAnalyzer(client_service, ai_enhancer=ai_enhancer)
    return _Services(
        client_service=client_service,
        auth_service=auth_service,
        audience_analyzer=audience_analyzer,
    )


def get_client_service() -> TelegramClientService:
    return _build_services().client_service


def get_auth_service() -> AuthServicePort:
    return _build_services().auth_service


def get_audience_analyzer() -> AudienceAnalyzerPort:
    return _build_services().audience_analyzer


def get_gigachat_status() -> GigaChatStatus:
    if not is_gigachat_configured():
        return GigaChatStatus(
            enabled=False,
            available=False,
            provider="gigachat",
            model=None,
            auth_mode=None,
            message="GigaChat не настроен: добавь в .env GIGACHAT_AUTH_KEY.",
        )

    try:
        settings = load_gigachat_settings()
        auth_mode = "auth_key" if settings.authorization_key else "credentials"
        enhancer = GigaChatAudienceEnhancer(settings)
        enhancer.validate_connection()
        return GigaChatStatus(
            enabled=True,
            available=True,
            provider="gigachat",
            model=settings.model,
            auth_mode=auth_mode,
            message="GigaChat настроен и токен получен.",
        )
    except Exception as exc:
        return GigaChatStatus(
            enabled=True,
            available=False,
            provider="gigachat",
            model=None,
            auth_mode=None,
            message=f"GigaChat найден в .env, но не инициализировался: {exc}",
        )
