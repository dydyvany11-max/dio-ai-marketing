from typing import Protocol

from src.api.services.dto import (
    AuthStatus,
    AuthorizedUser,
    GigaChatStatus,
    QRCodePayload,
    TelegramAudienceReport,
)


class AuthServicePort(Protocol):
    async def get_status(self) -> AuthStatus:
        ...

    async def is_user_authorized(self) -> bool:
        ...

    async def create_qr_payload(self) -> QRCodePayload:
        ...

    async def create_qr_url(self) -> tuple[str, str | None]:
        ...

    async def authorize_with_password(self, password: str) -> AuthorizedUser:
        ...

    async def get_current_user(self) -> AuthorizedUser:
        ...


class AudienceAnalyzerPort(Protocol):
    async def analyze(
        self,
        source: str,
        participant_limit: int = 200,
        message_limit: int = 100,
    ) -> TelegramAudienceReport:
        ...


class AIStatusPort(Protocol):
    def get_status(self) -> GigaChatStatus:
        ...
