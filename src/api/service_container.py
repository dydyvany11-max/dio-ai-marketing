from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from src.api.config import (
    get_analysis_settings,
    get_storage_settings,
    is_gigachat_configured,
    load_gigachat_settings,
    load_settings,
)
from src.api.services.audiance.ai import GigaChatAudienceEnhancer
from src.api.services.audiance.analyzer import TelegramAudienceAnalyzer
from src.api.services.audiance.repository import SqlAlchemyAudienceAnalysisRepository
from src.api.services.auth import TelegramAuthService
from src.api.services.dto import GigaChatStatus
from src.api.services.interfaces import (
    AudienceAnalysisRepositoryPort,
    AudienceAnalyzerPort,
    AuthServicePort,
)
from src.api.services.telegram_client import TelegramClientService


@dataclass(frozen=True)
class ServiceContainer:
    client_service: TelegramClientService
    auth_service: AuthServicePort
    audience_analyzer: AudienceAnalyzerPort
    analysis_repository: AudienceAnalysisRepositoryPort


def build_service_container() -> ServiceContainer:
    settings = load_settings()
    analysis_settings = get_analysis_settings()
    storage_settings = get_storage_settings()
    client_service = TelegramClientService(settings)
    auth_service = TelegramAuthService(client_service)
    analysis_repository = SqlAlchemyAudienceAnalysisRepository(
        storage_settings.resolved_sqlite_db_path
    )

    ai_enhancer = None
    if is_gigachat_configured():
        ai_enhancer = GigaChatAudienceEnhancer(
            load_gigachat_settings(),
            analysis_settings=analysis_settings,
        )

    audience_analyzer = TelegramAudienceAnalyzer(
        client_service,
        ai_enhancer=ai_enhancer,
        analysis_repository=analysis_repository,
        analysis_settings=analysis_settings,
    )
    return ServiceContainer(
        client_service=client_service,
        auth_service=auth_service,
        audience_analyzer=audience_analyzer,
        analysis_repository=analysis_repository,
    )


@lru_cache(maxsize=1)
def get_service_container() -> ServiceContainer:
    return build_service_container()


def build_gigachat_status() -> GigaChatStatus:
    if not is_gigachat_configured():
        return GigaChatStatus(
            enabled=False,
            available=False,
            provider="gigachat",
            model=None,
            auth_mode=None,
            message="GigaChat не настроен: добавь в .env GIGACHAT_AUTH_KEY или GIGACHAT_CREDENTIALS.",
        )

    try:
        settings = load_gigachat_settings()
        enhancer = GigaChatAudienceEnhancer(settings)
        enhancer.validate_connection()
        return GigaChatStatus(
            enabled=True,
            available=True,
            provider="gigachat",
            model=settings.model,
            auth_mode="credentials",
            message="GigaChat настроен и доступен.",
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
