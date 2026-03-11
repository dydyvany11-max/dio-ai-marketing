from config import load_settings
from services.auth import TelegramAuthService
from services.interfaces import AuthServicePort, PostAnalyzerPort
from services.post_analyzer import TelegramPostAnalyzer
from services.telegram_client import TelegramClientService
from services.url_parser import RegexTelegramPostUrlParser

_settings = load_settings()
_client_service = TelegramClientService(_settings)
_auth_service = TelegramAuthService(_client_service)
_post_analyzer = TelegramPostAnalyzer(_client_service, RegexTelegramPostUrlParser())


def get_client_service() -> TelegramClientService:
    return _client_service


def get_auth_service() -> AuthServicePort:
    return _auth_service


def get_post_analyzer() -> PostAnalyzerPort:
    return _post_analyzer
