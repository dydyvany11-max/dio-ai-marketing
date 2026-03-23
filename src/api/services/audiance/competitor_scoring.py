from __future__ import annotations

from src.api.services.audiance.competitor_models import CompetitorMatchEvaluation
from src.api.services.audiance.constants import GENERIC_THEME_KEYS
from src.api.services.audiance.text_processing import AudienceTextProcessor
from src.api.services.dto import (
    AudienceCluster,
    ChannelTheme,
    ContentInsights,
    EngagementMetrics,
    TelegramAudienceReport,
)


class AudienceCompetitorScorer:
    def __init__(self, text_processor: AudienceTextProcessor) -> None:
        self._text_processor = text_processor

    def evaluate(
        self,
        base_report: TelegramAudienceReport,
        candidate_report: TelegramAudienceReport,
    ) -> CompetitorMatchEvaluation:
        (
            theme_similarity,
            matched_themes,
            matched_specific_themes,
            matched_generic_themes,
        ) = self._theme_similarity(
            base_report.channel_themes,
            candidate_report.channel_themes,
        )
        keyword_similarity, matched_keywords = self._keyword_similarity(
            base_report.channel_themes,
            candidate_report.channel_themes,
        )
        interest_similarity = self._cluster_overlap(
            base_report.interest_clusters,
            candidate_report.interest_clusters,
        )
        audience_similarity = interest_similarity
        engagement_similarity = self._engagement_similarity(
            base_report.engagement_metrics,
            candidate_report.engagement_metrics,
        )
        format_similarity = self._format_similarity(
            base_report.content_insights,
            candidate_report.content_insights,
        )
        dominant_theme_bonus = (
            1.0
            if (
                base_report.dominant_theme.key == candidate_report.dominant_theme.key
                and base_report.dominant_theme.key not in GENERIC_THEME_KEYS
            )
            else 0.0
        )
        niche_overlap = self._niche_theme_overlap(
            base_report.channel_themes,
            candidate_report.channel_themes,
        )
        dominant_specific_theme = self._dominant_specific_theme_label(base_report.channel_themes)
        candidate_dominant_specific_theme = self._dominant_specific_theme_label(
            candidate_report.channel_themes
        )
        shared_theme_count = len(matched_themes)
        shared_specific_theme_count = len(matched_specific_themes)
        generic_overlap_count = len(matched_generic_themes)
        disqualifiers = self._build_competitor_disqualifiers(
            dominant_specific_theme=dominant_specific_theme,
            candidate_dominant_specific_theme=candidate_dominant_specific_theme,
            shared_specific_theme_count=shared_specific_theme_count,
            generic_overlap_count=generic_overlap_count,
            niche_overlap=niche_overlap,
            dominant_theme_bonus=dominant_theme_bonus,
            keyword_similarity=keyword_similarity,
        )

        similarity_score = (
            0.30 * theme_similarity
            + 0.18 * keyword_similarity
            + 0.14 * interest_similarity
            + 0.14 * audience_similarity
            + 0.14 * engagement_similarity
            + 0.08 * format_similarity
            + 0.06 * dominant_theme_bonus
        )
        if theme_similarity < 0.18 and keyword_similarity < 0.12:
            similarity_score *= 0.72
        if dominant_theme_bonus == 0.0 and interest_similarity < 0.2:
            similarity_score *= 0.84
        if shared_specific_theme_count == 0:
            similarity_score *= 0.48
        elif shared_specific_theme_count == 1:
            similarity_score *= 0.8
        if niche_overlap == 0.0:
            similarity_score *= 0.72
        elif niche_overlap < 0.15:
            similarity_score *= 0.86
        if matched_generic_themes and not matched_specific_themes:
            similarity_score *= 0.74

        relation_type = self._classify_competitor_relation(
            dominant_specific_theme=dominant_specific_theme,
            candidate_dominant_specific_theme=candidate_dominant_specific_theme,
            shared_theme_count=shared_theme_count,
            shared_specific_theme_count=shared_specific_theme_count,
            similarity_score=similarity_score,
            theme_similarity=theme_similarity,
            keyword_similarity=keyword_similarity,
            interest_similarity=interest_similarity,
            audience_similarity=audience_similarity,
            niche_overlap=niche_overlap,
            dominant_theme_bonus=dominant_theme_bonus,
            disqualifiers=disqualifiers,
        )

        return CompetitorMatchEvaluation(
            theme_similarity=theme_similarity,
            keyword_similarity=keyword_similarity,
            interest_similarity=interest_similarity,
            audience_similarity=audience_similarity,
            engagement_similarity=engagement_similarity,
            format_similarity=format_similarity,
            dominant_theme_bonus=dominant_theme_bonus,
            niche_overlap=niche_overlap,
            dominant_specific_theme=dominant_specific_theme,
            candidate_dominant_specific_theme=candidate_dominant_specific_theme,
            matched_themes=matched_themes,
            matched_specific_themes=matched_specific_themes,
            matched_generic_themes=matched_generic_themes,
            matched_keywords=matched_keywords,
            shared_theme_count=shared_theme_count,
            shared_specific_theme_count=shared_specific_theme_count,
            generic_overlap_count=generic_overlap_count,
            disqualifiers=disqualifiers,
            similarity_score=similarity_score,
            relation_type=relation_type,
        )

    @staticmethod
    def _theme_similarity(
        base_themes: list[ChannelTheme],
        candidate_themes: list[ChannelTheme],
    ) -> tuple[float, list[str], list[str], list[str]]:
        base_ranked = AudienceCompetitorScorer._specific_then_generic_themes(base_themes)
        candidate_ranked = AudienceCompetitorScorer._specific_then_generic_themes(candidate_themes)
        base_map = {theme.key: theme for theme in base_ranked}
        candidate_map = {theme.key: theme for theme in candidate_ranked}
        overlap_keys = [key for key in base_map if key in candidate_map]
        score = 0.0
        for index, key in enumerate([theme.key for theme in base_ranked[:5]]):
            if key not in candidate_map:
                continue
            rank_weight = 1.0 if index == 0 else 0.75 if index == 1 else 0.55
            if key in GENERIC_THEME_KEYS:
                rank_weight *= 0.22
            score += min(base_map[key].share, candidate_map[key].share) * rank_weight
        matched_labels = [base_map[key].label for key in overlap_keys]
        matched_specific_labels = [
            base_map[key].label
            for key in overlap_keys
            if key not in GENERIC_THEME_KEYS
        ]
        matched_generic_labels = [
            base_map[key].label
            for key in overlap_keys
            if key in GENERIC_THEME_KEYS
        ]
        return (
            max(0.0, min(score * 1.35, 1.0)),
            matched_labels,
            matched_specific_labels,
            matched_generic_labels,
        )

    @staticmethod
    def _classify_competitor_relation(
        *,
        dominant_specific_theme: str | None,
        candidate_dominant_specific_theme: str | None,
        shared_theme_count: int,
        shared_specific_theme_count: int,
        similarity_score: float,
        theme_similarity: float,
        keyword_similarity: float,
        interest_similarity: float,
        audience_similarity: float,
        niche_overlap: float,
        dominant_theme_bonus: float,
        disqualifiers: list[str],
    ) -> str:
        if "нет общих нишевых тем" in disqualifiers:
            if (
                shared_theme_count >= 2
                and keyword_similarity >= 0.1
                and audience_similarity >= 0.45
            ):
                return "смежный конкурент"
            return "широкий рыночный сосед"

        if (
            shared_specific_theme_count >= 2
            and keyword_similarity >= 0.16
            and (theme_similarity >= 0.28 or niche_overlap >= 0.2)
            and (
                dominant_specific_theme is None
                or candidate_dominant_specific_theme is None
                or dominant_specific_theme == candidate_dominant_specific_theme
            )
        ) or (
            shared_specific_theme_count >= 2
            and dominant_theme_bonus > 0.0
            and keyword_similarity >= 0.2
            and interest_similarity >= 0.4
        ):
            return "прямой конкурент"

        if (
            similarity_score >= 0.5
            and "нет общих нишевых тем" not in disqualifiers
            and "совпадение только по широким темам" not in disqualifiers
        ):
            return "прямой конкурент"

        if (
            shared_specific_theme_count >= 1
            or (
                shared_theme_count >= 2
                and niche_overlap >= 0.08
                and keyword_similarity >= 0.12
            )
            or (
                dominant_theme_bonus > 0.0
                and theme_similarity >= 0.24
                and keyword_similarity >= 0.12
            )
        ):
            return "смежный конкурент"

        return "широкий рыночный сосед"

    @staticmethod
    def _dominant_specific_theme_label(themes: list[ChannelTheme]) -> str | None:
        for theme in themes:
            if theme.key not in GENERIC_THEME_KEYS:
                return theme.label
        return None

    @staticmethod
    def _build_competitor_disqualifiers(
        *,
        dominant_specific_theme: str | None,
        candidate_dominant_specific_theme: str | None,
        shared_specific_theme_count: int,
        generic_overlap_count: int,
        niche_overlap: float,
        dominant_theme_bonus: float,
        keyword_similarity: float,
    ) -> list[str]:
        disqualifiers: list[str] = []
        if shared_specific_theme_count == 0:
            disqualifiers.append("нет общих нишевых тем")
        if generic_overlap_count > 0 and shared_specific_theme_count == 0:
            disqualifiers.append("совпадение только по широким темам")
        if (
            dominant_specific_theme
            and candidate_dominant_specific_theme
            and dominant_specific_theme != candidate_dominant_specific_theme
            and shared_specific_theme_count == 0
        ):
            disqualifiers.append("разные доминирующие ниши")
        if niche_overlap < 0.08 and shared_specific_theme_count < 2:
            disqualifiers.append("слабое нишевое пересечение")
        if dominant_theme_bonus == 0.0 and keyword_similarity < 0.12:
            disqualifiers.append("нет сильного совпадения по ключевым сигналам")
        return disqualifiers

    @staticmethod
    def _keyword_similarity(
        base_themes: list[ChannelTheme],
        candidate_themes: list[ChannelTheme],
    ) -> tuple[float, list[str]]:
        base_weights: dict[str, float] = {}
        candidate_weights: dict[str, float] = {}
        for index, theme in enumerate(AudienceCompetitorScorer._specific_then_generic_themes(base_themes)[:5]):
            theme_weight = 1.0 if index == 0 else 0.7 if index == 1 else 0.45
            if theme.key in GENERIC_THEME_KEYS:
                theme_weight *= 0.4
            for keyword in theme.evidence[:5]:
                normalized = keyword.lower()
                base_weights[normalized] = max(base_weights.get(normalized, 0.0), theme_weight)
        for index, theme in enumerate(
            AudienceCompetitorScorer._specific_then_generic_themes(candidate_themes)[:5]
        ):
            theme_weight = 1.0 if index == 0 else 0.7 if index == 1 else 0.45
            if theme.key in GENERIC_THEME_KEYS:
                theme_weight *= 0.4
            for keyword in theme.evidence[:5]:
                normalized = keyword.lower()
                candidate_weights[normalized] = max(
                    candidate_weights.get(normalized, 0.0),
                    theme_weight,
                )

        if not base_weights or not candidate_weights:
            return 0.0, []
        matched = sorted(set(base_weights) & set(candidate_weights))
        union = set(base_weights) | set(candidate_weights)
        numerator = sum(min(base_weights[key], candidate_weights[key]) for key in matched)
        denominator = sum(
            max(base_weights.get(key, 0.0), candidate_weights.get(key, 0.0))
            for key in union
        )
        score = numerator / denominator if denominator else 0.0
        return score, matched

    @staticmethod
    def _niche_theme_overlap(
        base_themes: list[ChannelTheme],
        candidate_themes: list[ChannelTheme],
    ) -> float:
        base_map = {
            theme.key: theme.share
            for theme in base_themes
            if theme.key not in GENERIC_THEME_KEYS
        }
        candidate_map = {
            theme.key: theme.share
            for theme in candidate_themes
            if theme.key not in GENERIC_THEME_KEYS
        }
        if not base_map or not candidate_map:
            return 0.0
        overlap_keys = set(base_map) & set(candidate_map)
        return sum(min(base_map[key], candidate_map[key]) for key in overlap_keys)

    @staticmethod
    def _specific_then_generic_themes(themes: list[ChannelTheme]) -> list[ChannelTheme]:
        specific = [theme for theme in themes if theme.key not in GENERIC_THEME_KEYS]
        generic = [theme for theme in themes if theme.key in GENERIC_THEME_KEYS]
        return specific + generic

    @staticmethod
    def _cluster_overlap(
        base_clusters: list[AudienceCluster],
        candidate_clusters: list[AudienceCluster],
    ) -> float:
        base_map = {cluster.key: cluster.share for cluster in base_clusters}
        candidate_map = {cluster.key: cluster.share for cluster in candidate_clusters}
        common_keys = set(base_map) | set(candidate_map)
        if not common_keys:
            return 0.0
        overlap = sum(
            min(base_map.get(key, 0.0), candidate_map.get(key, 0.0))
            for key in common_keys
        )
        return max(0.0, min(overlap, 1.0))

    @staticmethod
    def _engagement_similarity(
        base_metrics: EngagementMetrics,
        candidate_metrics: EngagementMetrics,
    ) -> float:
        def closeness(left: float, right: float, scale: float) -> float:
            if scale <= 0:
                return 1.0 if left == right else 0.0
            return max(0.0, 1.0 - abs(left - right) / scale)

        return (
            closeness(base_metrics.view_rate, candidate_metrics.view_rate, 1.0)
            + closeness(
                base_metrics.deep_engagement_rate,
                candidate_metrics.deep_engagement_rate,
                0.2,
            )
            + closeness(base_metrics.posts_per_day, candidate_metrics.posts_per_day, 20.0)
        ) / 3

    def _format_similarity(
        self,
        base_content: ContentInsights,
        candidate_content: ContentInsights,
    ) -> float:
        base_tokens = set(
            self._text_processor.tokenize(
                f"{base_content.channel_format} {base_content.strongest_content_hook}"
            )
        )
        candidate_tokens = set(
            self._text_processor.tokenize(
                f"{candidate_content.channel_format} {candidate_content.strongest_content_hook}"
            )
        )
        if not base_tokens or not candidate_tokens:
            return 0.0
        return len(base_tokens & candidate_tokens) / len(base_tokens | candidate_tokens)
