from __future__ import annotations

import logging
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import mean, median
from typing import Iterable
from urllib.parse import urlparse

from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.types import (
    Channel,
    Chat,
    User,
    UserStatusLastMonth,
    UserStatusLastWeek,
    UserStatusOffline,
    UserStatusOnline,
    UserStatusRecently,
)

from src.api.services.dto import (
    AudienceCluster,
    ContentInsights,
    EngagementMetrics,
    AudiencePersona,
    AudienceSource,
    ChannelTheme,
    TelegramAudienceReport,
)
from src.api.services.audience_presenters import (
    build_summary,
    translate_cluster,
    translate_source,
    translate_theme,
)
from src.api.services.audience_constants import (
    AGE_BUCKETS,
    AGE_SIGNAL_WEIGHTS,
    INTEREST_PATTERNS,
    STOPWORDS,
    THEME_LABELS,
)
from src.api.services.errors import AuthorizationRequiredError, TelegramOperationError
from src.api.services.telegram_client import TelegramClientService

logger = logging.getLogger(__name__)

class _MessageStats:
    def __init__(
        self,
        text: str,
        date: datetime,
        views: int,
        forwards: int,
        replies: int,
        reactions: int,
    ):
        self.text = text
        self.date = date
        self.views = views
        self.forwards = forwards
        self.replies = replies
        self.reactions = reactions


class TelegramAudienceAnalyzer:
    def __init__(self, client_service: TelegramClientService, ai_enhancer=None):
        self._client_service = client_service
        self._ai_enhancer = ai_enhancer

    async def analyze(
        self,
        source: str,
        participant_limit: int = 200,
        message_limit: int = 100,
    ) -> TelegramAudienceReport:
        await self._client_service.ensure_connected()
        client = self._client_service.client

        if not await client.is_user_authorized():
            raise AuthorizationRequiredError("Telegram session is not authorized")

        entity = await self._resolve_entity(source)
        participants_estimate = await self._get_participants_estimate(entity)
        participants, participant_warnings = await self._collect_participants(
            entity,
            participant_limit,
        )
        messages = await self._collect_messages(entity, message_limit)
        texts = [message.text for message in messages]

        interest_clusters, category_scores, theme_evidence = self._build_interest_clusters(texts)
        if participants:
            activity_clusters = self._build_activity_clusters(participants)
            age_clusters = self._build_age_clusters(participants)
            audience_segments = self._build_audience_segments(participants)
        else:
            activity_clusters = self._build_channel_activity_clusters(
                messages,
                participants_estimate,
            )
            age_clusters = self._build_channel_age_clusters(
                category_scores,
                messages,
                participants_estimate,
            )
            audience_segments = self._build_channel_audience_segments(
                activity_clusters,
                participants_estimate,
            )
        channel_themes = self._build_channel_themes(category_scores, theme_evidence)
        dominant_theme = channel_themes[0] if channel_themes else ChannelTheme(
            key="не_определено",
            label="тема не определена",
            share=0.0,
            evidence=["недостаточно контентных сигналов"],
        )
        source_info = AudienceSource(
            source=source,
            title=getattr(entity, "title", None) or self._display_name(entity),
            entity_id=getattr(entity, "id", 0),
            entity_type=self._entity_type(entity),
            username=getattr(entity, "username", None),
            participants_estimate=participants_estimate,
            participant_sample_size=len(participants),
            message_sample_size=len(messages),
        )
        top_active_segment = max(audience_segments, key=lambda cluster: cluster.share)
        engagement_metrics = self._build_engagement_metrics(messages, participants_estimate)
        if self._ai_enhancer is None:
            audience_persona = self._build_audience_persona(
                source_info,
                top_active_segment,
                age_clusters,
                interest_clusters,
                dominant_theme,
                messages,
            )
            content_insights = self._build_content_insights(
                dominant_theme=dominant_theme,
                top_active_segment=top_active_segment,
                engagement_metrics=engagement_metrics,
                channel_themes=channel_themes,
                messages=messages,
            )
            summary = build_summary(
                source_info=source_info,
                activity_clusters=activity_clusters,
                age_clusters=age_clusters,
                interest_clusters=interest_clusters,
            )
            ai_message = "AI-слой не подключен, поэтому смысловые выводы собраны базовой моделью."
        else:
            audience_persona = self._build_ai_pending_persona()
            content_insights = self._build_ai_pending_content_insights()
            summary = self._build_ai_pending_summary(source_info)
            ai_message = "Фактические метрики собраны. Смысловой портрет и рекомендации должен достроить GigaChat."

        limitations = [
            "Telegram API не отдает точный возраст и точные интересы пользователей.",
            "Кластеры интересов выводятся по содержанию последних сообщений канала или чата.",
        ]
        if participants:
            limitations.append(
                "Возрастные кластеры оцениваются по открытым признакам профилей участников из выборки."
            )
        else:
            limitations.append(
                "Для каналов без доступа к подписчикам возраст и активность оцениваются по вовлеченности и контентным сигналам."
            )
        limitations.extend(participant_warnings)

        report = TelegramAudienceReport(
            ai_enhanced=False,
            ai_message=ai_message,
            source=translate_source(source_info),
            activity_clusters=[translate_cluster(cluster) for cluster in activity_clusters],
            age_clusters=[translate_cluster(cluster) for cluster in age_clusters],
            interest_clusters=[translate_cluster(cluster) for cluster in interest_clusters],
            audience_segments=[translate_cluster(cluster) for cluster in audience_segments],
            top_active_segment=translate_cluster(top_active_segment),
            dominant_theme=translate_theme(dominant_theme),
            channel_themes=[translate_theme(theme) for theme in channel_themes],
            audience_persona=audience_persona,
            engagement_metrics=engagement_metrics,
            content_insights=content_insights,
            summary=summary,
            limitations=limitations,
        )
        if self._ai_enhancer is None:
            return TelegramAudienceReport(
                ai_enhanced=False,
                ai_message=ai_message,
                source=report.source,
                activity_clusters=report.activity_clusters,
                age_clusters=report.age_clusters,
                interest_clusters=report.interest_clusters,
                audience_segments=report.audience_segments,
                top_active_segment=report.top_active_segment,
                dominant_theme=report.dominant_theme,
                channel_themes=report.channel_themes,
                audience_persona=self._build_audience_persona(
                    source_info,
                    top_active_segment,
                    age_clusters,
                    interest_clusters,
                    dominant_theme,
                    messages,
                ),
                engagement_metrics=report.engagement_metrics,
                content_insights=self._build_content_insights(
                    dominant_theme=dominant_theme,
                    top_active_segment=top_active_segment,
                    engagement_metrics=engagement_metrics,
                    channel_themes=channel_themes,
                    messages=messages,
                ),
                summary=build_summary(
                    source_info=source_info,
                    activity_clusters=activity_clusters,
                    age_clusters=age_clusters,
                    interest_clusters=interest_clusters,
                ),
                limitations=report.limitations,
            )
        try:
            return self._ai_enhancer.enhance(report)
        except Exception as exc:
            logger.warning("GigaChat audience enhancement failed: %s", exc)
            return TelegramAudienceReport(
                ai_enhanced=False,
                ai_message=f"GigaChat РЅРµ СЃРјРѕРі СѓР»СѓС‡С€РёС‚СЊ Р°РЅР°Р»РёР·: {exc}",
                source=report.source,
                activity_clusters=report.activity_clusters,
                age_clusters=report.age_clusters,
                interest_clusters=report.interest_clusters,
                audience_segments=report.audience_segments,
                top_active_segment=report.top_active_segment,
                dominant_theme=report.dominant_theme,
                channel_themes=report.channel_themes,
                audience_persona=report.audience_persona,
                engagement_metrics=report.engagement_metrics,
                content_insights=report.content_insights,
                summary=report.summary,
                limitations=report.limitations,
            )
    async def _resolve_entity(self, source: str):
        client = self._client_service.client
        normalized = self._normalize_source(source)

        if normalized.lstrip("-").isdigit():
            numeric_id = int(normalized)
            resolved = await self._find_dialog_by_id(numeric_id)
            if resolved is not None:
                return resolved

        try:
            return await client.get_entity(normalized)
        except Exception as exc:
            raise TelegramOperationError(
                f"Failed to resolve Telegram source '{source}': {exc}"
            ) from exc

    @staticmethod
    def _normalize_source(source: str) -> str:
        value = source.strip()
        if not value:
            raise TelegramOperationError("source is required")

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

    async def _find_dialog_by_id(self, numeric_id: int):
        normalized_id = abs(numeric_id)
        if str(normalized_id).startswith("100") and len(str(normalized_id)) > 10:
            normalized_id = int(str(normalized_id)[3:])

        async for dialog in self._client_service.client.iter_dialogs():
            entity = dialog.entity
            if getattr(entity, "id", None) == normalized_id:
                return entity
        return None

    async def _get_participants_estimate(self, entity) -> int | None:
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

    async def _collect_participants(self, entity, limit: int) -> tuple[list[User], list[str]]:
        users: list[User] = []
        warnings: list[str] = []

        try:
            async for participant in self._client_service.client.iter_participants(
                entity,
                limit=limit,
            ):
                if isinstance(participant, User):
                    users.append(participant)
        except Exception as exc:
            warnings.append(
                "Выборка участников неполная, потому что Telegram ограничил доступ к списку подписчиков или требует права администратора."
            )

        return users, warnings

    async def _collect_messages(self, entity, limit: int) -> list[_MessageStats]:
        messages: list[_MessageStats] = []
        try:
            async for message in self._client_service.client.iter_messages(entity, limit=limit):
                if message.message:
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
                        _MessageStats(
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

    def _build_activity_clusters(self, users: Iterable[User]) -> list[AudienceCluster]:
        counters = Counter()
        for user in users:
            counters[self._activity_bucket(user)] += 1

        labels = {
            "high": "Высокая активность",
            "medium": "Средняя активность",
            "low": "Низкая активность",
            "unknown": "Активность не видна",
            "unavailable": "Недостаточно данных",
        }
        notes = {
            "high": ["онлайн, недавно онлайн или был в сети не более 3 дней назад"],
            "medium": ["был онлайн на этой неделе или в последние 30 дней"],
            "low": ["был онлайн больше 30 дней назад"],
            "unknown": ["статус последнего посещения скрыт"],
            "unavailable": ["выборка участников недоступна"],
        }
        return self._clusters_from_counter(counters, labels, "unavailable", notes, "high")

    def _build_age_clusters(self, users: Iterable[User]) -> list[AudienceCluster]:
        counters = Counter()
        for user in users:
            counters[self._age_bucket(user)] += 1

        labels = {
            "13-17": "13-17",
            "18-24": "18-24",
            "25-34": "25-34",
            "35-44": "35-44",
            "45+": "45+",
            "unknown": "Не удалось оценить",
        }
        notes = {
            bucket: ["оценка только по открытым признакам имени и username"]
            for bucket in labels
        }
        return self._clusters_from_counter(counters, labels, "unknown", notes, "low")

    def _build_interest_clusters(self, texts: list[str]) -> tuple[list[AudienceCluster], Counter, dict[str, list[str]]]:
        token_counts = Counter()
        category_counts = Counter()
        evidence_map: dict[str, Counter] = {}

        for text in texts:
            tokens = self._tokenize(text)
            token_counts.update(tokens)
            for token in tokens:
                for category, patterns in INTEREST_PATTERNS.items():
                    if any(token.startswith(pattern) for pattern in patterns):
                        category_counts[category] += 1
                        evidence_map.setdefault(category, Counter())[token] += 1

        labels = {
            "marketing": "Маркетинг и продажи",
            "business": "Бизнес и продукт",
            "education": "Обучение и карьера",
            "technology": "Технологии и AI",
            "media_lifestyle": "Медиа и лайфстайл",
            "news_current": "Новости и актуальная повестка",
            "humor_memes": "Мемы и развлечения",
            "finance_crypto": "Финансы и crypto",
        }

        if not category_counts:
            top_keywords = [word for word, _ in token_counts.most_common(5)]
            return [
                AudienceCluster(
                    key="undetermined",
                    label="Темы не определились",
                    count=0,
                    share=0.0,
                    confidence="low",
                    notes=top_keywords or ["в последних сообщениях недостаточно тематических сигналов"],
                )
            ], category_counts, {}

        total = sum(category_counts.values())
        clusters = []
        for key, count in category_counts.most_common():
            keywords = [word for word, _ in evidence_map.get(key, Counter()).most_common(5)]
            clusters.append(
                AudienceCluster(
                    key=key,
                    label=labels[key],
                    count=count,
                    share=round(count / total, 4),
                    confidence="medium" if count >= 3 else "low",
                    notes=keywords or ["категория выведена по словам из последних постов"],
                )
            )
        return clusters, category_counts, {
            key: [word for word, _ in evidence_map.get(key, Counter()).most_common(5)]
            for key in category_counts
        }

    def _build_channel_themes(
        self,
        category_scores: Counter,
        theme_evidence: dict[str, list[str]],
    ) -> list[ChannelTheme]:
        if not category_scores:
            return []

        adjusted = Counter(category_scores)
        if adjusted.get("news_current", 0) and adjusted.get("technology", 0):
            adjusted["news_current"] += adjusted["technology"] * 0.35
        if adjusted.get("humor_memes", 0) and adjusted.get("news_current", 0):
            adjusted["humor_memes"] += adjusted["news_current"] * 0.15
        if adjusted.get("media_lifestyle", 0) and adjusted.get("humor_memes", 0):
            adjusted["humor_memes"] += adjusted["media_lifestyle"] * 0.2

        total = sum(adjusted.values()) or 1
        themes = []
        for key, score in adjusted.most_common():
            if score <= 0:
                continue
            themes.append(
                ChannelTheme(
                    key=self._translate_key(key),
                    label=THEME_LABELS.get(key, key),
                    share=round(score / total, 4),
                    evidence=theme_evidence.get(key, ["контентный сигнал канала"]),
                )
            )
        return themes

    def _build_audience_persona(
        self,
        source_info: AudienceSource,
        top_active_segment: AudienceCluster,
        age_clusters: list[AudienceCluster],
        interest_clusters: list[AudienceCluster],
        dominant_theme: ChannelTheme,
        messages: list[_MessageStats],
    ) -> AudiencePersona:
        top_age = max(age_clusters, key=lambda cluster: cluster.share) if age_clusters else None
        top_interest = max(interest_clusters, key=lambda cluster: cluster.share) if interest_clusters else None
        posting_density = self._posting_density(messages)
        prime_time_share = self._prime_time_share(messages)

        if prime_time_share >= 0.5:
            activity_pattern = "Чаще вовлекается в вечерние часы и регулярно реагирует на свежие публикации."
        elif posting_density >= 12:
            activity_pattern = "Потребляет контент в течение дня короткими сессиями и хорошо реагирует на частый постинг."
        else:
            activity_pattern = "Вовлекается точечно, чаще на сильные или важные публикации."

        age_text = top_age.label if top_age else "без выраженного возраста"
        interest_text = top_interest.label if top_interest else dominant_theme.label

        motivations = [
            f"Следить за темой '{dominant_theme.label}' без лишнего шума.",
            f"Получать контент, который совпадает с интересом '{interest_text}'.",
            "Быстро понимать, что сейчас важно или обсуждаемо.",
        ]
        content_preferences = [
            f"Контент с тематикой '{dominant_theme.label}'.",
            "Короткие, быстро считываемые публикации с сильным заголовком.",
            "Посты, которые можно переслать или обсудить.",
        ]
        title = f"Ядро аудитории канала {source_info.title}"
        description = (
            f"Основной пользователь похож на сегмент '{top_active_segment.label}', "
            f"чаще всего относится к возрастной группе '{age_text}' и приходит за тематикой "
            f"'{interest_text}'."
        )
        return AudiencePersona(
            title=title,
            description=description,
            motivations=motivations,
            content_preferences=content_preferences,
            activity_pattern=activity_pattern,
        )

    def _build_engagement_metrics(
        self,
        messages: list[_MessageStats],
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
        posts_per_day = self._posting_density(messages)
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

    def _build_content_insights(
        self,
        dominant_theme: ChannelTheme,
        top_active_segment: AudienceCluster,
        engagement_metrics: EngagementMetrics,
        channel_themes: list[ChannelTheme],
        messages: list[_MessageStats],
    ) -> ContentInsights:
        second_theme = channel_themes[1].label if len(channel_themes) > 1 else dominant_theme.label
        if dominant_theme.label == "новости и актуальная повестка":
            channel_format = "Новостной канал с быстрым реактивным контентом"
        elif dominant_theme.label == "мемы и развлекательный контент":
            channel_format = "Развлекательный канал с мемным ядром"
        else:
            channel_format = f"Контентный канал с фокусом на тему '{dominant_theme.label}'"

        if engagement_metrics.deep_engagement_rate >= 0.045:
            strongest_content_hook = "Лучше всего заходят посты, которые хочется переслать дальше и обсудить."
        elif engagement_metrics.view_rate >= 0.25:
            strongest_content_hook = "Лучше всего работает быстрый, легко считываемый контент с сильным заголовком."
        else:
            strongest_content_hook = "Лучше всего срабатывают точечные публикации с понятной пользой для аудитории."

        posting_recommendations = [
            f"Держать в основе тему '{dominant_theme.label}', а второй линией усиливать '{second_theme}'.",
            "Чаще публиковать короткие посты с сильной первой строкой и понятным тезисом.",
            f"Опираться на сегмент '{top_active_segment.label}', потому что именно он сейчас формирует основную вовлеченность.",
        ]
        if engagement_metrics.posts_per_day >= 20:
            posting_recommendations.append("Не разгонять частоту публикаций ещё сильнее: лучше повышать качество и пересылаемость постов.")
        else:
            posting_recommendations.append("Можно аккуратно увеличить частоту публикаций, если сохранить темп и качество подачи.")

        best_for_growth = [
            "Посты, которые можно быстро переслать знакомым или в чат.",
            "Короткие новости, дайджесты и реакции на актуальную повестку.",
            "Публикации на стыке основной тематики канала и второго по силе интереса аудитории.",
        ]
        if any("мем" in theme.label for theme in channel_themes):
            best_for_growth.append("Лёгкие мемные или ироничные вставки вокруг главной темы канала.")

        return ContentInsights(
            channel_format=channel_format,
            strongest_content_hook=strongest_content_hook,
            posting_recommendations=posting_recommendations,
            best_for_growth=best_for_growth,
        )

    def _build_channel_activity_clusters(
        self,
        messages: list[_MessageStats],
        participants_estimate: int | None,
    ) -> list[AudienceCluster]:
        if not messages or not participants_estimate:
            return [
                AudienceCluster(
                    key="unavailable",
                    label="Недостаточно данных",
                    count=0,
                    share=0.0,
                    confidence="low",
                    notes=["недостаточно сообщений или нет оценки размера аудитории"],
                )
            ]

        avg_views = mean(message.views for message in messages)
        median_views = median(message.views for message in messages)
        avg_forwards = mean(message.forwards for message in messages)
        avg_replies = mean(message.replies for message in messages)
        avg_reactions = mean(message.reactions for message in messages)
        view_rate = min(avg_views / participants_estimate, 1.0)
        deep_engagement = (
            (avg_forwards + avg_replies + avg_reactions) / avg_views
            if avg_views else 0.0
        )
        posting_density = self._posting_density(messages)

        engaged_share = self._clamp(
            0.45 * view_rate + 1.8 * deep_engagement + 0.12 * posting_density,
            0.05,
            0.55,
        )
        warm_share = self._clamp(
            0.95 * view_rate - 0.55 * engaged_share + 0.08 * posting_density,
            0.15,
            0.5,
        )
        passive_share = self._clamp(1.0 - engaged_share - warm_share, 0.1, 0.8)

        normalized_total = engaged_share + warm_share + passive_share
        engaged_share /= normalized_total
        warm_share /= normalized_total
        passive_share /= normalized_total

        return [
            self._estimated_cluster(
                "high",
                "Высокая активность",
                engaged_share,
                participants_estimate,
                "medium",
                [
                    f"средняя доля просмотров {view_rate:.3f}",
                    f"медиана просмотров {int(median_views)}",
                    f"глубокая вовлеченность {deep_engagement:.4f}",
                ],
            ),
            self._estimated_cluster(
                "medium",
                "Средняя активность",
                warm_share,
                participants_estimate,
                "medium",
                [
                    f"частота публикаций {posting_density:.2f} поста/день",
                    f"среднее число пересылок {int(avg_forwards)}",
                ],
            ),
            self._estimated_cluster(
                "low",
                "Низкая активность",
                passive_share,
                participants_estimate,
                "medium",
                ["оценка как оставшаяся часть аудитории вне активного ядра"],
            ),
        ]

    def _build_channel_age_clusters(
        self,
        category_scores: Counter,
        messages: list[_MessageStats],
        participants_estimate: int | None,
    ) -> list[AudienceCluster]:
        if not participants_estimate:
            participants_estimate = max(len(messages), 1)

        age_scores = Counter()
        for bucket, weights in AGE_SIGNAL_WEIGHTS.items():
            for category, multiplier in weights.items():
                age_scores[bucket] += category_scores.get(category, 0) * multiplier

        avg_text_len = mean(len(message.text) for message in messages) if messages else 0.0
        if avg_text_len > 350:
            age_scores["35-44"] += 2.0
            age_scores["45+"] += 1.0
        elif avg_text_len > 180:
            age_scores["25-34"] += 2.0
            age_scores["35-44"] += 1.0
        else:
            age_scores["18-24"] += 1.0
            age_scores["25-34"] += 0.5

        prime_hours_share = self._prime_time_share(messages)
        if prime_hours_share >= 0.55:
            age_scores["25-34"] += 1.2
            age_scores["35-44"] += 0.8
        else:
            age_scores["18-24"] += 0.8

        if not age_scores:
            age_scores["25-34"] = 1.0

        total = sum(age_scores.values())
        clusters = []
        for bucket, _, _ in AGE_BUCKETS:
            score = age_scores.get(bucket, 0.0)
            if score <= 0:
                continue
            share = score / total
            clusters.append(
                self._estimated_cluster(
                    bucket,
                    bucket,
                    share,
                    participants_estimate,
                    "low",
                    ["оценка по тематике контента, длине текстов и времени публикаций"],
                )
            )
        return sorted(clusters, key=lambda cluster: cluster.share, reverse=True)

    def _build_channel_audience_segments(
        self,
        activity_clusters: list[AudienceCluster],
        participants_estimate: int | None,
    ) -> list[AudienceCluster]:
        if not participants_estimate:
            return [
                AudienceCluster(
                    key="unavailable",
                    label="Недостаточно данных",
                    count=0,
                    share=0.0,
                    confidence="low",
                    notes=["оценка размера аудитории недоступна"],
                )
            ]

        activity_map = {cluster.key: cluster for cluster in activity_clusters}
        core_share = activity_map.get("high").share if activity_map.get("high") else 0.0
        warm_share = activity_map.get("medium").share if activity_map.get("medium") else 0.0
        passive_share = activity_map.get("low").share if activity_map.get("low") else 1.0
        bot_share = self._clamp(0.015 + passive_share * 0.04, 0.01, 0.06)
        passive_share = max(passive_share - bot_share, 0.0)
        total = core_share + warm_share + passive_share + bot_share
        core_share /= total
        warm_share /= total
        passive_share /= total
        bot_share /= total

        return [
            self._estimated_cluster(
                "core_active",
                "Ядро активной аудитории",
                core_share,
                participants_estimate,
                "medium",
                ["сегмент построен по доле аудитории с высокой вовлеченностью"],
            ),
            self._estimated_cluster(
                "warm_audience",
                "Тёплая аудитория",
                warm_share,
                participants_estimate,
                "medium",
                ["сегмент построен по доле аудитории со средней вовлеченностью"],
            ),
            self._estimated_cluster(
                "silent_audience",
                "Пассивная аудитория",
                passive_share,
                participants_estimate,
                "medium",
                ["оценка как подписчики с низким взаимодействием с контентом"],
            ),
            self._estimated_cluster(
                "bots",
                "Боты и сервисные аккаунты",
                bot_share,
                participants_estimate,
                "low",
                ["эвристическая доля для неактивных и технических аккаунтов"],
            ),
        ]

    def _build_audience_segments(self, users: Iterable[User]) -> list[AudienceCluster]:
        counters = Counter()
        for user in users:
            if getattr(user, "bot", False):
                counters["bots"] += 1
                continue

            activity = self._activity_bucket(user)
            if activity == "high":
                counters["core_active"] += 1
            elif activity == "medium":
                counters["warm_audience"] += 1
            else:
                counters["silent_audience"] += 1

        labels = {
            "core_active": "Ядро активной аудитории",
            "warm_audience": "Тёплая аудитория",
            "silent_audience": "Пассивная аудитория",
            "bots": "Боты и сервисные аккаунты",
            "unavailable": "Недостаточно данных",
        }
        notes = {
            "core_active": ["регулярная недавняя активность"],
            "warm_audience": ["активность была на неделе или в течение месяца"],
            "silent_audience": ["давняя активность или скрытый статус"],
            "bots": ["Telegram пометил аккаунт как bot"],
            "unavailable": ["выборка участников недоступна"],
        }
        return self._clusters_from_counter(counters, labels, "unavailable", notes, "medium")

    def _activity_bucket(self, user: User) -> str:
        status = getattr(user, "status", None)
        now = datetime.now(timezone.utc)

        if isinstance(status, (UserStatusOnline, UserStatusRecently)):
            return "high"
        if isinstance(status, UserStatusLastWeek):
            return "medium"
        if isinstance(status, UserStatusLastMonth):
            return "low"
        if isinstance(status, UserStatusOffline):
            was_online = getattr(status, "was_online", None)
            if was_online is None:
                return "unknown"
            if was_online.tzinfo is None:
                was_online = was_online.replace(tzinfo=timezone.utc)
            delta = now - was_online
            if delta <= timedelta(days=3):
                return "high"
            if delta <= timedelta(days=30):
                return "medium"
            return "low"
        return "unknown"

    def _age_bucket(self, user: User) -> str:
        text = " ".join(
            part for part in (
                getattr(user, "username", None),
                getattr(user, "first_name", None),
                getattr(user, "last_name", None),
            )
            if part
        )

        year_match = re.search(r"(19[5-9]\d|20[0-1]\d)", text)
        if not year_match:
            return "unknown"

        year = int(year_match.group(1))
        age = datetime.now().year - year
        if age < 13 or age > 80:
            return "unknown"

        for bucket, min_age, max_age in AGE_BUCKETS:
            if min_age <= age <= max_age:
                return bucket
        return "unknown"

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        tokens = re.findall(r"[A-Za-zА-Яа-яЁё]{4,}", text.lower())
        return [token for token in tokens if token not in STOPWORDS]

    @staticmethod
    def _clusters_from_counter(
        counter: Counter,
        labels: dict[str, str],
        fallback_key: str,
        notes_map: dict[str, list[str]],
        confidence: str,
    ) -> list[AudienceCluster]:
        total = sum(counter.values())
        if total == 0:
            return [
                AudienceCluster(
                    key=fallback_key,
                    label=labels[fallback_key],
                    count=0,
                    share=0.0,
                    confidence=confidence,
                    notes=notes_map.get(fallback_key, []),
                )
            ]

        result = []
        for key, label in labels.items():
            count = counter.get(key, 0)
            if count == 0:
                continue
            result.append(
                AudienceCluster(
                    key=key,
                    label=label,
                    count=count,
                    share=round(count / total, 4),
                    confidence=confidence,
                    notes=notes_map.get(key, []),
                )
            )
        return result

    @staticmethod
    def _estimated_cluster(
        key: str,
        label: str,
        share: float,
        population: int,
        confidence: str,
        notes: list[str],
    ) -> AudienceCluster:
        bounded_share = max(0.0, min(share, 1.0))
        count = int(round(population * bounded_share))
        return AudienceCluster(
            key=key,
            label=label,
            count=count,
            share=round(bounded_share, 4),
            confidence=confidence,
            notes=notes,
        )

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    @staticmethod
    def _posting_density(messages: list[_MessageStats]) -> float:
        if len(messages) < 2:
            return 0.0
        dates = sorted(message.date for message in messages)
        span_days = max((dates[-1] - dates[0]).total_seconds() / 86400, 1 / 24)
        return len(messages) / span_days

    @staticmethod
    def _prime_time_share(messages: list[_MessageStats]) -> float:
        if not messages:
            return 0.0
        count = sum(1 for message in messages if 17 <= message.date.hour <= 22)
        return count / len(messages)

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
            part for part in (
                getattr(entity, "first_name", None),
                getattr(entity, "last_name", None),
            )
            if part
        ) or "Неизвестно"

