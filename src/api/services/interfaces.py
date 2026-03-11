from typing import Protocol

from services.dto import AuthStatus, AuthorizedUser, QRCodePayload, TelegramPostAnalysis


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


class PostAnalyzerPort(Protocol):
    async def analyze(self, url: str) -> TelegramPostAnalysis:
        ...
