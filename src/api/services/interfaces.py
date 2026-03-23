from typing import Protocol

from src.api.services.dto import (
    AudienceAnalysisSnapshot,
    AuthStatus,
    AuthorizedUser,
    CompetitorDiscoveryReport,
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
        message_limit: int = 100,
    ) -> TelegramAudienceReport:
        ...

    async def compare_competitors(
        self,
        source: str,
        message_limit: int = 100,
        top_k: int = 5,
    ) -> CompetitorDiscoveryReport:
        ...


class AudienceAnalysisRepositoryPort(Protocol):
    def save_analysis(self, snapshot: AudienceAnalysisSnapshot) -> None:
        ...

    def get_latest_analysis(self, source_key: str) -> AudienceAnalysisSnapshot | None:
        ...
