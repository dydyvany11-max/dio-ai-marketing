from __future__ import annotations

import logging

from src.api.services.audiance.competitor_matcher import AudienceCompetitorMatcher
from src.api.services.audiance.internal_models import MessageStats
from src.api.services.audiance.presenters import (
    build_summary,
    translate_cluster,
    translate_source,
    translate_theme,
)
from src.api.services.audiance.report_builder import AudienceReportBuilder
from src.api.services.audiance.snapshot import (
    build_audience_analysis_snapshot,
    normalize_source_key,
    restore_audience_report,
)
from src.api.services.audiance.telegram_channel_reader import TelegramChannelReader
from src.api.services.audiance.telegram_competitor_search import TelegramCompetitorSearch
from src.api.services.audiance.telegram_source_resolver import TelegramSourceResolver
from src.api.services.audiance.text_processing import AudienceTextProcessor
from src.api.services.dto import (
    ChannelTheme,
    CompetitorDiscoveryReport,
    CompetitorFailure,
    TelegramAudienceReport,
)
from src.api.services.errors import AIEnhancementError, AuthorizationRequiredError, TelegramOperationError
from src.api.services.interfaces import AudienceAnalysisRepositoryPort
from src.api.services.telegram_client import TelegramClientService

logger = logging.getLogger(__name__)
AI_KEYWORD_MESSAGE_LIMIT = 12


class TelegramAudienceAnalyzer:
    def __init__(
        self,
        client_service: TelegramClientService,
        ai_enhancer=None,
        analysis_repository: AudienceAnalysisRepositoryPort | None = None,
        text_processor: AudienceTextProcessor | None = None,
        report_builder: AudienceReportBuilder | None = None,
        competitor_matcher: AudienceCompetitorMatcher | None = None,
        source_resolver: TelegramSourceResolver | None = None,
        channel_reader: TelegramChannelReader | None = None,
        competitor_search: TelegramCompetitorSearch | None = None,
    ):
        self._client_service = client_service
        self._ai_enhancer = ai_enhancer
        self._analysis_repository = analysis_repository

        shared_text_processor = text_processor
        if shared_text_processor is None and report_builder is not None:
            shared_text_processor = report_builder.text_processor

        self._report_builder = report_builder or AudienceReportBuilder(shared_text_processor)
        self._competitor_matcher = competitor_matcher or AudienceCompetitorMatcher(
            self._report_builder.text_processor
        )
        self._source_resolver = source_resolver or TelegramSourceResolver(client_service)
        self._channel_reader = channel_reader or TelegramChannelReader(client_service)
        self._competitor_search = competitor_search or TelegramCompetitorSearch(
            client_service,
            self._source_resolver,
        )

    async def analyze(
        self,
        source: str,
        message_limit: int = 100,
    ) -> TelegramAudienceReport:
        await self._source_resolver.ensure_authorized()
        entity = await self._source_resolver.resolve_entity(source)
        return await self._analyze_entity(
            entity=entity,
            source=source,
            message_limit=message_limit,
        )

    async def compare_competitors(
        self,
        source: str,
        message_limit: int = 100,
        top_k: int = 5,
    ) -> CompetitorDiscoveryReport:
        await self._source_resolver.ensure_authorized()
        raw_analyzer = self._build_raw_analyzer()
        base_report = await raw_analyzer._get_cached_or_analyze(
            source=source,
            message_limit=message_limit,
        )
        discovered_candidates = await self._competitor_search.discover_candidates(
            search_queries=self._competitor_matcher.build_search_queries(base_report),
            limit_per_query=8,
            exclude_source=source,
        )
        if not discovered_candidates:
            raise TelegramOperationError(
                "Telegram search did not return competitor candidates for this channel"
            )

        base_normalized = self._source_resolver.normalize_source(source)
        seen_candidates: set[str] = set()
        matches = []
        failures: list[CompetitorFailure] = []

        for candidate_source, candidate_entity in discovered_candidates:
            normalized_candidate = self._source_resolver.normalize_source(candidate_source)
            if normalized_candidate == base_normalized or normalized_candidate in seen_candidates:
                continue
            seen_candidates.add(normalized_candidate)

            try:
                candidate_report = await raw_analyzer._get_cached_candidate_or_analyze(
                    candidate_source=candidate_source,
                    candidate_entity=candidate_entity,
                    message_limit=message_limit,
                )
                match = self._competitor_matcher.build_match(base_report, candidate_report)
                match = self._competitor_matcher.enhance_match_reason(
                    base_report=base_report,
                    candidate_report=candidate_report,
                    match=match,
                    ai_enhancer=self._ai_enhancer,
                )
                matches.append(match)
            except (AuthorizationRequiredError, TelegramOperationError) as exc:
                failures.append(CompetitorFailure(source=candidate_source, error=str(exc)))

        return CompetitorDiscoveryReport(
            source=base_report.source,
            discovered_candidates=[item_source for item_source, _ in discovered_candidates],
            competitors=self._competitor_matcher.select_top_matches(matches, top_k=top_k),
            failed_candidates=failures,
        )

    async def _get_cached_or_analyze(
        self,
        source: str,
        message_limit: int = 100,
    ) -> TelegramAudienceReport:
        if self._analysis_repository is not None:
            snapshot = self._analysis_repository.get_latest_analysis(normalize_source_key(source))
            if snapshot is not None:
                return restore_audience_report(snapshot)
        return await self.analyze(source=source, message_limit=message_limit)

    async def _analyze_entity(
        self,
        *,
        entity,
        source: str,
        message_limit: int,
    ) -> TelegramAudienceReport:
        participants_estimate = await self._channel_reader.get_participants_estimate(entity)
        messages = await self._channel_reader.collect_messages(entity, message_limit)
        message_samples = [message.text.strip() for message in messages if message.text.strip()][:20]
        ai_keywords = self._extract_ai_keywords(messages)

        post_topic_profiles = self._report_builder.build_post_topic_profiles(messages, ai_keywords)
        interest_clusters, category_scores, theme_evidence = self._report_builder.build_interest_clusters(
            post_topic_profiles
        )
        channel_themes = self._report_builder.build_channel_themes(category_scores, theme_evidence)
        dominant_theme = channel_themes[0] if channel_themes else self._default_dominant_theme()
        source_info = self._source_resolver.build_source_info(
            entity=entity,
            source=source,
            participants_estimate=participants_estimate,
            message_sample_size=len(messages),
        )
        engagement_metrics = self._report_builder.build_engagement_metrics(messages, participants_estimate)
        audience_persona = self._report_builder.build_audience_persona(
            source_info,
            interest_clusters,
            dominant_theme,
            messages,
        )
        content_insights = self._report_builder.build_content_insights(
            dominant_theme,
            engagement_metrics,
        )
        summary = build_summary(
            source_info=source_info,
            interest_clusters=interest_clusters,
        )

        if self._ai_enhancer is None:
            ai_message = "AI-слой не подключен, поэтому портрет аудитории собран локально по контенту канала."
        else:
            ai_message = "Метрики постов собраны. GigaChat достраивает портрет целевой аудитории и рекомендации."

        report = TelegramAudienceReport(
            ai_enhanced=False,
            ai_message=ai_message,
            source=translate_source(source_info),
            message_samples=message_samples,
            interest_clusters=[translate_cluster(cluster) for cluster in interest_clusters],
            dominant_theme=translate_theme(dominant_theme),
            channel_themes=[translate_theme(theme) for theme in channel_themes],
            audience_persona=audience_persona,
            engagement_metrics=engagement_metrics,
            content_insights=content_insights,
            summary=summary,
            limitations=[
                "Портрет аудитории строится по содержанию последних постов и метрикам постов, а не по данным профилей подписчиков.",
                "Telegram API не даёт надёжных характеристик подписчиков, поэтому пользовательские эвристики отключены.",
                "Кластеры интересов выводятся по содержанию последних сообщений канала или чата.",
            ],
        )

        if self._ai_enhancer is not None:
            try:
                report = self._ai_enhancer.enhance(report)
            except AIEnhancementError:
                raise
            except Exception as exc:
                logger.warning("GigaChat audience enhancement failed: %s", exc)
                raise AIEnhancementError(str(exc)) from exc

        self._persist_analysis(report)
        return report

    def _build_raw_analyzer(self) -> TelegramAudienceAnalyzer:
        return TelegramAudienceAnalyzer(
            self._client_service,
            ai_enhancer=None,
            analysis_repository=self._analysis_repository,
            report_builder=self._report_builder,
            competitor_matcher=self._competitor_matcher,
            source_resolver=self._source_resolver,
            channel_reader=self._channel_reader,
            competitor_search=self._competitor_search,
        )

    async def _get_cached_candidate_or_analyze(
        self,
        *,
        candidate_source: str,
        candidate_entity,
        message_limit: int,
    ) -> TelegramAudienceReport:
        if self._analysis_repository is not None:
            snapshot = self._analysis_repository.get_latest_analysis(normalize_source_key(candidate_source))
            if snapshot is not None:
                return restore_audience_report(snapshot)
        return await self._analyze_entity(
            entity=candidate_entity,
            source=candidate_source,
            message_limit=message_limit,
        )

    def _extract_ai_keywords(self, messages: list[MessageStats]) -> dict[int, list[str]]:
        if self._ai_enhancer is None or not hasattr(self._ai_enhancer, "extract_post_keywords_batch"):
            return {}
        try:
            limited_messages = messages[:AI_KEYWORD_MESSAGE_LIMIT]
            return self._ai_enhancer.extract_post_keywords_batch(
                [message.text for message in limited_messages]
            )
        except Exception as exc:
            logger.warning("GigaChat keyword extraction failed: %s", exc)
            return {}

    def _persist_analysis(self, report: TelegramAudienceReport) -> None:
        if self._analysis_repository is None:
            return
        try:
            snapshot = build_audience_analysis_snapshot(report)
            self._analysis_repository.save_analysis(snapshot)
        except Exception as exc:
            logger.warning("Audience analysis persistence failed: %s", exc)

    @staticmethod
    def _default_dominant_theme() -> ChannelTheme:
        return ChannelTheme(
            key="not_determined",
            label="тема не определена",
            share=0.0,
            evidence=["недостаточно контентных сигналов"],
        )
