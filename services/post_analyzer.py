from datetime import timezone

from services.dto import TelegramPostAnalysis
from services.errors import (
    AuthorizationRequiredError,
    TelegramOperationError,
    TelegramPostNotFoundError,
)
from services.telegram_client import TelegramClientService
from services.url_parser import TelegramPostUrlParser


class TelegramPostAnalyzer:
    def __init__(
        self,
        client_service: TelegramClientService,
        url_parser: TelegramPostUrlParser,
    ):
        self._client_service = client_service
        self._url_parser = url_parser

    async def analyze(self, url: str) -> TelegramPostAnalysis:
        await self._client_service.ensure_connected()
        client = self._client_service.client

        if not await client.is_user_authorized():
            raise AuthorizationRequiredError("Authorize first via /tg/auth/qr")

        channel, message_id = self._url_parser.parse(url)

        try:
            entity = await client.get_entity(channel)
            msg = await client.get_messages(entity, ids=message_id)
        except Exception as exc:
            raise TelegramOperationError(f"Failed to fetch post: {exc}") from exc

        if not msg:
            raise TelegramPostNotFoundError("Post not found")

        date_iso = self._to_iso_utc(msg.date)
        return TelegramPostAnalysis(
            url=url,
            channel=channel,
            message_id=message_id,
            text=msg.message or "",
            date_iso=date_iso,
            views=getattr(msg, "views", None),
            forwards=getattr(msg, "forwards", None),
        )

    @staticmethod
    def _to_iso_utc(value) -> str | None:
        if not value:
            return None
        if value.tzinfo:
            return value.astimezone(timezone.utc).isoformat()
        return value.replace(tzinfo=timezone.utc).isoformat()
