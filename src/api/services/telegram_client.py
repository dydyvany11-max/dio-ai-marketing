from telethon import TelegramClient

from src.api.config import TelegramSettings
from src.api.services.errors import TelegramOperationError


class TelegramClientService:
    def __init__(self, settings: TelegramSettings):
        self._client = TelegramClient(
            settings.session_path,
            settings.api_id,
            settings.api_hash,
        )

    @property
    def client(self) -> TelegramClient:
        return self._client

    async def ensure_connected(self) -> None:
        if not self._client.is_connected():
            try:
                await self._client.connect()
            except Exception as exc:
                raise TelegramOperationError(
                    f"Failed to connect to Telegram: {exc}"
                ) from exc

    async def disconnect(self) -> None:
        if self._client.is_connected():
            await self._client.disconnect()
