from __future__ import annotations

from src.api.services.audiance.cluster_builder import AudienceClusterBuilder
from src.api.services.audiance.engagement_builder import AudienceEngagementBuilder
from src.api.services.audiance.internal_models import MessageStats, PostTopicProfile
from src.api.services.audiance.text_processing import AudienceTextProcessor
from src.api.services.audiance.topic_profiler import AudienceTopicProfiler
from src.api.services.dto import (
    AudienceCluster,
    AudiencePersona,
    AudienceSource,
    ChannelTheme,
    ContentInsights,
    EngagementMetrics,
)

GENERIC_CLUSTER_TOKENS = {
    "канал",
    "пост",
    "тема",
    "темы",
    "новость",
    "новости",
    "сообщение",
    "сообщения",
    "текст",
    "контент",
    "автор",
    "подписчик",
    "подписчики",
    "группа",
    "telegram",
}


class AudienceReportBuilder:
    def __init__(
        self,
        text_processor: AudienceTextProcessor | None = None,
        *,
        topic_profiler: AudienceTopicProfiler | None = None,
        cluster_builder: AudienceClusterBuilder | None = None,
        engagement_builder: AudienceEngagementBuilder | None = None,
    ) -> None:
        self._text_processor = text_processor or AudienceTextProcessor(
            generic_cluster_tokens=GENERIC_CLUSTER_TOKENS
        )
        self._topic_profiler = topic_profiler or AudienceTopicProfiler(self._text_processor)
        self._cluster_builder = cluster_builder or AudienceClusterBuilder(self._text_processor)
        self._engagement_builder = engagement_builder or AudienceEngagementBuilder()

    @property
    def text_processor(self) -> AudienceTextProcessor:
        return self._text_processor

    def build_post_topic_profiles(
        self,
        messages: list[MessageStats],
        ai_keywords: dict[int, list[str]],
    ) -> list[PostTopicProfile]:
        return self._topic_profiler.build_post_topic_profiles(messages, ai_keywords)

    def analyze_post_topics(
        self,
        text: str,
        keyword_phrases: list[str] | None = None,
    ) -> PostTopicProfile:
        return self._topic_profiler.analyze_post_topics(text, keyword_phrases)

    def build_interest_clusters(
        self,
        post_profiles: list[PostTopicProfile],
    ) -> tuple[list[AudienceCluster], dict[str, int], dict[str, list[str]]]:
        return self._cluster_builder.build_interest_clusters(post_profiles)

    def build_channel_themes(
        self,
        category_scores: dict[str, int],
        theme_evidence: dict[str, list[str]],
    ) -> list[ChannelTheme]:
        return self._cluster_builder.build_channel_themes(category_scores, theme_evidence)

    def build_audience_persona(
        self,
        source_info: AudienceSource,
        interest_clusters: list[AudienceCluster],
        dominant_theme: ChannelTheme,
        messages: list[MessageStats],
    ) -> AudiencePersona:
        top_interest = max(interest_clusters, key=lambda cluster: cluster.share) if interest_clusters else None
        posting_density = self._engagement_builder.posting_density(messages)
        prime_time_share = self._engagement_builder.prime_time_share(messages)

        if prime_time_share >= 0.5:
            activity_pattern = "Аудитория чаще реагирует в вечерние часы и на свежие публикации."
        elif posting_density >= 12:
            activity_pattern = (
                "Аудитория потребляет контент короткими сессиями в течение дня "
                "и нормально воспринимает частый постинг."
            )
        else:
            activity_pattern = "Аудитория вовлекается точечно, в основном на сильные или важные публикации."

        interest_text = top_interest.label if top_interest else dominant_theme.label
        age_range = self._estimate_age_range(interest_clusters, dominant_theme)
        motivations = [
            f"Следить за темой '{dominant_theme.label}' без лишнего шума.",
            f"Получать контент, который совпадает с интересом '{interest_text}'.",
            "Быстро понимать, что сейчас важно и обсуждаемо.",
        ]
        content_preferences = [
            f"Контент с фокусом на тему '{dominant_theme.label}'.",
            "Короткие посты с сильным заголовком и быстрым смысловым заходом.",
            "Публикации, которые легко переслать или обсудить.",
        ]
        title = f"Основная аудитория канала {source_info.title}"
        description = (
            f"Вероятная целевая аудитория канала приходит за темой '{interest_text}', "
            f"чаще всего попадает в возрастной диапазон {age_range} "
            f"и лучше всего реагирует на контент в доминирующем формате '{dominant_theme.label}'."
        )
        persona_summary = (
            f"Это человек с устойчивым интересом к теме '{interest_text}', который воспринимает канал "
            f"как полезный источник ориентиров, идей или новостей и предпочитает быстро считывать смысл поста."
        )
        return AudiencePersona(
            title=title,
            description=description,
            age_range=age_range,
            persona_summary=persona_summary,
            motivations=motivations,
            content_preferences=content_preferences,
            activity_pattern=activity_pattern,
        )

    @staticmethod
    def _estimate_age_range(
        interest_clusters: list[AudienceCluster],
        dominant_theme: ChannelTheme,
    ) -> str:
        weights = {
            "18-24": 0.4,
            "25-34": 1.0,
            "35-44": 0.6,
            "45+": 0.2,
        }
        theme_keys = [cluster.key for cluster in interest_clusters[:3]]
        theme_keys.append(dominant_theme.key)
        for key in theme_keys:
            if key in {"education", "gaming", "media_lifestyle", "humor_memes"}:
                weights["18-24"] += 1.2
                weights["25-34"] += 0.4
            elif key in {"marketing", "technology", "career_jobs"}:
                weights["25-34"] += 1.4
                weights["18-24"] += 0.5
                weights["35-44"] += 0.5
            elif key in {"business", "finance_crypto", "real_estate", "construction"}:
                weights["25-34"] += 0.9
                weights["35-44"] += 1.3
                weights["45+"] += 0.5
            elif key in {"news_current", "medicine_health", "auto_transport"}:
                weights["25-34"] += 0.7
                weights["35-44"] += 1.0
                weights["45+"] += 0.4
        return max(weights.items(), key=lambda item: item[1])[0]

    def build_engagement_metrics(
        self,
        messages: list[MessageStats],
        participants_estimate: int | None,
    ) -> EngagementMetrics:
        return self._engagement_builder.build_engagement_metrics(messages, participants_estimate)

    def build_content_insights(
        self,
        dominant_theme: ChannelTheme,
        engagement_metrics: EngagementMetrics,
    ) -> ContentInsights:
        return self._engagement_builder.build_content_insights(dominant_theme, engagement_metrics)

    @staticmethod
    def posting_density(messages: list[MessageStats]) -> float:
        return AudienceEngagementBuilder.posting_density(messages)

    @staticmethod
    def prime_time_share(messages: list[MessageStats]) -> float:
        return AudienceEngagementBuilder.prime_time_share(messages)
