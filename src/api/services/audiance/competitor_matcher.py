from __future__ import annotations

from src.api.services.audiance.competitor_queries import AudienceCompetitorQueryBuilder
from src.api.services.audiance.competitor_scoring import AudienceCompetitorScorer
from src.api.services.audiance.text_processing import AudienceTextProcessor
from src.api.services.dto import CompetitorMatch, TelegramAudienceReport


class AudienceCompetitorMatcher:
    def __init__(
        self,
        text_processor: AudienceTextProcessor,
        *,
        query_builder: AudienceCompetitorQueryBuilder | None = None,
        scorer: AudienceCompetitorScorer | None = None,
    ) -> None:
        self._query_builder = query_builder or AudienceCompetitorQueryBuilder()
        self._scorer = scorer or AudienceCompetitorScorer(text_processor)

    def build_search_queries(self, report: TelegramAudienceReport) -> list[str]:
        return self._query_builder.build_search_queries(report)

    def build_match(
        self,
        base_report: TelegramAudienceReport,
        candidate_report: TelegramAudienceReport,
    ) -> CompetitorMatch:
        evaluation = self._scorer.evaluate(base_report, candidate_report)

        reason_parts = [f"Тип: {evaluation.relation_type}"]
        if evaluation.matched_themes:
            reason_parts.append(
                f"Пересекающиеся темы: {', '.join(evaluation.matched_themes[:3])}"
            )
        if evaluation.matched_specific_themes:
            reason_parts.append(
                f"Нишевых общих тем: {evaluation.shared_specific_theme_count}"
            )
        elif evaluation.matched_generic_themes:
            reason_parts.append("Совпадение в основном по широким темам")
        if evaluation.matched_keywords:
            reason_parts.append(
                f"Общие сигналы контента: {', '.join(evaluation.matched_keywords[:4])}"
            )
        if evaluation.interest_similarity >= 0.6:
            reason_parts.append("Похожий набор интересов в контенте")
        if evaluation.engagement_similarity >= 0.65:
            reason_parts.append("Близкий ритм публикаций и вовлеченность")
        if evaluation.audience_similarity >= 0.65:
            reason_parts.append("Схожая структура аудитории")
        if evaluation.disqualifiers:
            reason_parts.append(f"Ограничения: {', '.join(evaluation.disqualifiers[:3])}")

        return CompetitorMatch(
            source=candidate_report.source,
            similarity_score=round(evaluation.similarity_score, 4),
            relation_type=evaluation.relation_type,
            audience_similarity=round(evaluation.audience_similarity, 4),
            engagement_similarity=round(evaluation.engagement_similarity, 4),
            format_similarity=round(evaluation.format_similarity, 4),
            shared_theme_count=evaluation.shared_theme_count,
            shared_specific_theme_count=evaluation.shared_specific_theme_count,
            dominant_specific_theme=evaluation.dominant_specific_theme,
            candidate_dominant_specific_theme=evaluation.candidate_dominant_specific_theme,
            matched_themes=evaluation.matched_themes[:5],
            matched_keywords=evaluation.matched_keywords[:6],
            disqualifiers=evaluation.disqualifiers,
            reason="; ".join(reason_parts),
        )

    def enhance_match_reason(
        self,
        *,
        base_report: TelegramAudienceReport,
        candidate_report: TelegramAudienceReport,
        match: CompetitorMatch,
        ai_enhancer,
    ) -> CompetitorMatch:
        if ai_enhancer is None or not hasattr(ai_enhancer, "explain_competitor_match"):
            return match

        try:
            reason = ai_enhancer.explain_competitor_match(
                base_report=base_report,
                candidate_report=candidate_report,
                match=match,
            )
        except Exception:
            return match

        return CompetitorMatch(
            source=match.source,
            similarity_score=match.similarity_score,
            relation_type=match.relation_type,
            audience_similarity=match.audience_similarity,
            engagement_similarity=match.engagement_similarity,
            format_similarity=match.format_similarity,
            shared_theme_count=match.shared_theme_count,
            shared_specific_theme_count=match.shared_specific_theme_count,
            dominant_specific_theme=match.dominant_specific_theme,
            candidate_dominant_specific_theme=match.candidate_dominant_specific_theme,
            matched_themes=match.matched_themes,
            matched_keywords=match.matched_keywords,
            disqualifiers=match.disqualifiers,
            reason=reason,
        )

    def select_top_matches(
        self,
        matches: list[CompetitorMatch],
        *,
        top_k: int,
    ) -> list[CompetitorMatch]:
        relation_rank = {
            "прямой конкурент": 2,
            "смежный конкурент": 1,
            "широкий рыночный сосед": 0,
        }
        filtered = [item for item in matches if self._should_keep_competitor(item)]
        filtered.sort(
            key=lambda item: (relation_rank.get(item.relation_type, -1), item.similarity_score),
            reverse=True,
        )
        return filtered[:top_k]

    @staticmethod
    def _should_keep_competitor(item: CompetitorMatch) -> bool:
        if item.relation_type in {"прямой конкурент", "смежный конкурент"}:
            return True
        return item.shared_specific_theme_count >= 1 and item.similarity_score >= 0.3
