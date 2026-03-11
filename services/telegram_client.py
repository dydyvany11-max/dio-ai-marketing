from telethon import TelegramClient

from config import TelegramSettings


class TelegramClientService:
    def __init__(self, settings: TelegramSettings):
        self._client = TelegramClient(
            settings.session_name,
            settings.api_id,
            settings.api_hash,
        )

    @property
    def client(self) -> TelegramClient:
        return self._client

    async def ensure_connected(self) -> None:
        if not self._client.is_connected():
            await self._client.connect()

    async def disconnect(self) -> None:
        if self._client.is_connected():
            await self._client.disconnect()
