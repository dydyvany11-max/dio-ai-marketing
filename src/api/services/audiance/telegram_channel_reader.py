from __future__ import annotations

from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.types import Channel, Chat

from src.api.services.audiance.internal_models import MessageStats
from src.api.services.errors import TelegramOperationError
from src.api.services.telegram_client import TelegramClientService


class TelegramChannelReader:
    def __init__(self, client_service: TelegramClientService) -> None:
        self._client_service = client_service

    async def get_participants_estimate(self, entity) -> int | None:
        client = self._client_service.client
        try:
            if isinstance(entity, Channel):
                full = await client(GetFullChannelRequest(entity))
                return getattr(full.full_chat, "participants_count", None)
            if isinstance(entity, Chat):
                full = await client(GetFullChatRequest(entity.id))
                participants = getattr(full.full_chat, "participants", None)
                if participants and getattr(participants, "participants", None):
                    return len(participants.participants)
        except Exception:
            return getattr(entity, "participants_count", None)
        return getattr(entity, "participants_count", None)

    async def collect_messages(self, entity, limit: int) -> list[MessageStats]:
        messages: list[MessageStats] = []
        try:
            async for message in self._client_service.client.iter_messages(entity, limit=limit):
                if not message.message:
                    continue

                reactions = 0
                reaction_obj = getattr(message, "reactions", None)
                if reaction_obj and getattr(reaction_obj, "results", None):
                    reactions = sum(
                        getattr(result, "count", 0)
                        for result in reaction_obj.results
                    )

                replies = 0
                replies_obj = getattr(message, "replies", None)
                if replies_obj:
                    replies = getattr(replies_obj, "replies", 0) or 0

                messages.append(
                    MessageStats(
                        text=message.message,
                        date=message.date,
                        views=getattr(message, "views", 0) or 0,
                        forwards=getattr(message, "forwards", 0) or 0,
                        replies=replies,
                        reactions=reactions,
                    )
                )
        except Exception as exc:
            raise TelegramOperationError(
                f"Failed to collect recent messages: {exc}"
            ) from exc
        return messages
