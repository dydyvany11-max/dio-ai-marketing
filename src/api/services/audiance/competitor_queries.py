from __future__ import annotations

from src.api.services.dto import TelegramAudienceReport


class AudienceCompetitorQueryBuilder:
    def build_search_queries(self, report: TelegramAudienceReport) -> list[str]:
        queries: list[str] = []
        for theme in report.channel_themes[:4]:
            label = (theme.label or "").strip()
            if label and label.lower() not in {item.lower() for item in queries}:
                queries.append(label)
            for keyword in theme.evidence[:2]:
                normalized_keyword = keyword.strip().lstrip("#")
                if not normalized_keyword:
                    continue
                if normalized_keyword.lower() in {item.lower() for item in queries}:
                    continue
                queries.append(normalized_keyword)
                if len(queries) >= 8:
                    return queries
        return queries or [report.dominant_theme.label]
