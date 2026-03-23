from __future__ import annotations

import logging

from telethon.tl.functions.messages import SearchGlobalRequest
from telethon.tl.types import InputMessagesFilterEmpty, InputPeerEmpty

from src.api.services.audiance.telegram_source_resolver import TelegramSourceResolver
from src.api.services.telegram_client import TelegramClientService

logger = logging.getLogger(__name__)


class TelegramCompetitorSearch:
    def __init__(
        self,
        client_service: TelegramClientService,
        source_resolver: TelegramSourceResolver,
    ) -> None:
        self._client_service = client_service
        self._source_resolver = source_resolver

    async def discover_candidates(
        self,
        *,
        search_queries: list[str],
        limit_per_query: int,
        exclude_source: str,
    ) -> list[tuple[str, object]]:
        discovered: list[tuple[str, object]] = []
        seen: set[str] = {self._source_resolver.normalize_source(exclude_source)}
        client = self._client_service.client

        for raw_query in search_queries:
            query = raw_query.strip().lstrip("#")
            if not query:
                continue

            try:
                response = await client(
                    SearchGlobalRequest(
                        q=query,
                        filter=InputMessagesFilterEmpty(),
                        min_date=None,
                        max_date=None,
                        offset_rate=0,
                        offset_peer=InputPeerEmpty(),
                        offset_id=0,
                        limit=limit_per_query,
                    )
                )
            except Exception as exc:
                logger.warning("Telegram competitor search failed for query '%s': %s", query, exc)
                continue

            for entity in getattr(response, "chats", []) or []:
                if not self._source_resolver.is_searchable_competitor_entity(entity):
                    continue
                candidate_source = self._source_resolver.entity_to_source(entity)
                if candidate_source is None:
                    continue
                normalized_candidate = self._source_resolver.normalize_source(candidate_source)
                if normalized_candidate in seen:
                    continue

                seen.add(normalized_candidate)
                discovered.append((candidate_source, entity))

        return discovered
