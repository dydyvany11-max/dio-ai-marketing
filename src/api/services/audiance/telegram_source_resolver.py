from __future__ import annotations

from urllib.parse import urlparse

from telethon.tl.types import Channel, Chat

from src.api.services.dto import AudienceSource
from src.api.services.errors import AuthorizationRequiredError, TelegramOperationError
from src.api.services.telegram_client import TelegramClientService


class TelegramSourceResolver:
    def __init__(self, client_service: TelegramClientService) -> None:
        self._client_service = client_service

    async def ensure_authorized(self) -> None:
        await self._client_service.ensure_connected()
        client = self._client_service.client
        if not await client.is_user_authorized():
            raise AuthorizationRequiredError("Telegram session is not authorized")

    async def resolve_entity(self, source: str):
        client = self._client_service.client
        normalized = self.normalize_source(source)

        if normalized.lstrip("-").isdigit():
            numeric_id = int(normalized)
            resolved = await self._find_dialog_by_id(numeric_id)
            if resolved is not None:
                return resolved

        try:
            return await client.get_entity(normalized)
        except Exception as exc:
            raise TelegramOperationError(
                f"Telegram source '{source}' was not found or is inaccessible: {exc}"
            ) from exc

    @staticmethod
    def normalize_source(source: str) -> str:
        value = source.strip()
        if not value:
            raise TelegramOperationError("source is required")

        if value.startswith("@"):
            value = value[1:]

        if value.startswith("http://") or value.startswith("https://"):
            parsed = urlparse(value)
            path = parsed.path.strip("/")
            if path.startswith("s/"):
                path = path[2:]
            first_segment = path.split("/", 1)[0]
            if not first_segment:
                raise TelegramOperationError("Telegram link must include channel or group")
            return first_segment

        return value

    @staticmethod
    def is_searchable_competitor_entity(entity) -> bool:
        return isinstance(entity, (Channel, Chat))

    @staticmethod
    def entity_to_source(entity) -> str | None:
        username = getattr(entity, "username", None)
        if username:
            return f"@{username}"

        entity_id = getattr(entity, "id", None)
        if entity_id is None:
            return None
        return str(entity_id)

    def build_source_info(
        self,
        *,
        entity,
        source: str,
        participants_estimate: int | None,
        message_sample_size: int,
    ) -> AudienceSource:
        return AudienceSource(
            source=source,
            title=getattr(entity, "title", None) or self._display_name(entity),
            entity_id=getattr(entity, "id", 0),
            entity_type=self._entity_type(entity),
            username=getattr(entity, "username", None),
            participants_estimate=participants_estimate,
            message_sample_size=message_sample_size,
        )

    async def _find_dialog_by_id(self, numeric_id: int):
        normalized_id = abs(numeric_id)
        if str(normalized_id).startswith("100") and len(str(normalized_id)) > 10:
            normalized_id = int(str(normalized_id)[3:])

        async for dialog in self._client_service.client.iter_dialogs():
            entity = dialog.entity
            if getattr(entity, "id", None) == normalized_id:
                return entity
        return None

    @staticmethod
    def _entity_type(entity) -> str:
        if isinstance(entity, Channel):
            if getattr(entity, "broadcast", False):
                return "channel"
            if getattr(entity, "megagroup", False):
                return "supergroup"
            return "channel_like"
        if isinstance(entity, Chat):
            return "group"
        return entity.__class__.__name__.lower()

    @staticmethod
    def _display_name(entity) -> str:
        if hasattr(entity, "title") and entity.title:
            return entity.title
        return " ".join(
            part
            for part in (
                getattr(entity, "first_name", None),
                getattr(entity, "last_name", None),
            )
            if part
        ) or "Неизвестно"
