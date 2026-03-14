from functools import lru_cache
from typing import NamedTuple

from src.api.config import (
    is_gigachat_configured,
    is_telegram_configured,
    is_vk_configured,
    load_gigachat_settings,
    load_settings,
    load_vk_settings,
)
from src.api.services.auth import TelegramAuthService
from src.api.services.audience import TelegramAudienceAnalyzer
from src.api.services.audience_ai import GigaChatAudienceEnhancer
from src.api.services.dto import GigaChatStatus
from src.api.services.interfaces import AuthServicePort, AudienceAnalyzerPort
from src.api.services.telegram_client import TelegramClientService
from src.api.services.vk_audience import VKAudienceAnalyzer
from src.api.services.vk_client import VKClient
from src.api.services.vk_publisher import VKPublisher


class _Services(NamedTuple):
    client_service: TelegramClientService | None
    auth_service: AuthServicePort | None
    audience_analyzer: AudienceAnalyzerPort | None
    vk_client: VKClient | None
    vk_audience: VKAudienceAnalyzer | None
    vk_publisher: VKPublisher | None


@lru_cache(maxsize=1)
def _build_services() -> _Services:
    client_service = None
    auth_service = None
    audience_analyzer = None
    if is_telegram_configured():
        settings = load_settings()
        client_service = TelegramClientService(settings)
        auth_service = TelegramAuthService(client_service)
        ai_enhancer = None
        if is_gigachat_configured():
            ai_enhancer = GigaChatAudienceEnhancer(load_gigachat_settings())
        audience_analyzer = TelegramAudienceAnalyzer(client_service, ai_enhancer=ai_enhancer)
    vk_client = None
    vk_audience = None
    vk_publisher = None
    if is_vk_configured():
        vk_client = VKClient(load_vk_settings())
        vk_audience = VKAudienceAnalyzer(vk_client)
        vk_publisher = VKPublisher(vk_client)
    return _Services(
        client_service=client_service,
        auth_service=auth_service,
        audience_analyzer=audience_analyzer,
        vk_client=vk_client,
        vk_audience=vk_audience,
        vk_publisher=vk_publisher,
    )


def get_client_service() -> TelegramClientService:
    service = _build_services().client_service
    if service is None:
        raise RuntimeError("Telegram is not configured")
    return service


def get_auth_service() -> AuthServicePort:
    service = _build_services().auth_service
    if service is None:
        raise RuntimeError("Telegram is not configured")
    return service


def get_audience_analyzer() -> AudienceAnalyzerPort:
    service = _build_services().audience_analyzer
    if service is None:
        raise RuntimeError("Telegram is not configured")
    return service


def get_vk_client() -> VKClient:
    client = _build_services().vk_client
    if client is None:
        raise RuntimeError("VK is not configured")
    return client


def get_vk_audience() -> VKAudienceAnalyzer:
    service = _build_services().vk_audience
    if service is None:
        raise RuntimeError("VK is not configured")
    return service


def get_vk_publisher() -> VKPublisher:
    service = _build_services().vk_publisher
    if service is None:
        raise RuntimeError("VK is not configured")
    return service


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
