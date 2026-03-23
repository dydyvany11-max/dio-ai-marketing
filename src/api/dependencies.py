from src.api.service_container import build_gigachat_status, get_service_container
from src.api.services.dto import GigaChatStatus
from src.api.services.interfaces import AudienceAnalyzerPort, AuthServicePort
from src.api.services.telegram_client import TelegramClientService


def get_client_service() -> TelegramClientService:
    return get_service_container().client_service


def get_auth_service() -> AuthServicePort:
    return get_service_container().auth_service


def get_audience_analyzer() -> AudienceAnalyzerPort:
    return get_service_container().audience_analyzer


def get_gigachat_status() -> GigaChatStatus:
    return build_gigachat_status()
