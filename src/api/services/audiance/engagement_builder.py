from __future__ import annotations

from statistics import mean, median

from src.api.services.audiance.content_insights import derive_content_insights
from src.api.services.audiance.internal_models import MessageStats
from src.api.services.dto import ChannelTheme, ContentInsights, EngagementMetrics


class AudienceEngagementBuilder:
    def build_engagement_metrics(
        self,
        messages: list[MessageStats],
        participants_estimate: int | None,
    ) -> EngagementMetrics:
        if not messages:
            return EngagementMetrics(0, 0, 0, 0, 0, 0.0, 0.0, 0.0)

        average_views = int(round(mean(message.views for message in messages)))
        median_views = int(round(median(message.views for message in messages)))
        average_forwards = int(round(mean(message.forwards for message in messages)))
        average_replies = int(round(mean(message.replies for message in messages)))
        average_reactions = int(round(mean(message.reactions for message in messages)))
        view_rate = average_views / participants_estimate if participants_estimate else 0.0
        deep_engagement_rate = (
            (average_forwards + average_replies + average_reactions) / average_views
            if average_views else 0.0
        )
        posts_per_day = self.posting_density(messages)
        return EngagementMetrics(
            average_views=average_views,
            median_views=median_views,
            average_forwards=average_forwards,
            average_replies=average_replies,
            average_reactions=average_reactions,
            view_rate=round(view_rate, 4),
            deep_engagement_rate=round(deep_engagement_rate, 4),
            posts_per_day=round(posts_per_day, 2),
        )

    def build_content_insights(
        self,
        dominant_theme: ChannelTheme,
        engagement_metrics: EngagementMetrics,
    ) -> ContentInsights:
        return derive_content_insights(dominant_theme, engagement_metrics)

    @staticmethod
    def posting_density(messages: list[MessageStats]) -> float:
        if len(messages) < 2:
            return 0.0
        dates = sorted(message.date for message in messages)
        span_days = max((dates[-1] - dates[0]).total_seconds() / 86400, 1 / 24)
        return len(messages) / span_days

    @staticmethod
    def prime_time_share(messages: list[MessageStats]) -> float:
        if not messages:
            return 0.0
        count = sum(1 for message in messages if 17 <= message.date.hour <= 22)
        return count / len(messages)
