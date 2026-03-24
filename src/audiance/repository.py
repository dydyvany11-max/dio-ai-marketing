from __future__ import annotations

from src.api.services.dto import AudienceAnalysisSnapshot
from src.api.services.interfaces import AudienceAnalysisRepositoryPort


class InMemoryAudienceAnalysisRepository(AudienceAnalysisRepositoryPort):
    def __init__(self) -> None:
        self._storage: dict[str, AudienceAnalysisSnapshot] = {}

    def save_analysis(self, snapshot: AudienceAnalysisSnapshot) -> None:
        self._storage[snapshot.source_key] = snapshot

    def get_latest_analysis(self, source_key: str) -> AudienceAnalysisSnapshot | None:
        return self._storage.get(source_key)
