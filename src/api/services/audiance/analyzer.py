from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime
from statistics import mean, median
from urllib.parse import urlparse

from nltk.collocations import (
    BigramAssocMeasures,
    BigramCollocationFinder,
    TrigramAssocMeasures,
    TrigramCollocationFinder,
)
from nltk.probability import FreqDist
from nltk.tokenize import RegexpTokenizer
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.types import Channel, Chat
from pymorphy3 import MorphAnalyzer

from src.api.services.dto import (
    AudienceCluster,
    CompetitorDiscoveryReport,
    CompetitorFailure,
    CompetitorMatch,
    ContentInsights,
    EngagementMetrics,
    AudiencePersona,
    AudienceSource,
    ChannelTheme,
    TelegramAudienceReport,
)
from src.api.services.audiance.presenters import (
    build_summary,
    translate_cluster,
    translate_key,
    translate_source,
    translate_theme,
)
from src.api.services.audiance.snapshot import build_audience_analysis_snapshot
from src.api.services.audiance.constants import (
    GENERIC_THEME_KEYS,
    INTEREST_PATTERNS,
    STOPWORDS,
    THEME_LABELS,
    THEME_SUBTOPIC_PATTERNS,
)
from src.api.services.errors import AIEnhancementError, AuthorizationRequiredError, TelegramOperationError
from src.api.services.interfaces import AudienceAnalysisRepositoryPort
from src.api.services.telegram_client import TelegramClientService

logger = logging.getLogger(__name__)
AI_KEYWORD_MESSAGE_LIMIT = 12
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


class _PostTopicProfile:
    def __init__(
        self,
        tokens: list[str],
        token_counts: Counter,
        category_scores: Counter,
        evidence_map: dict[str, Counter],
    ):
        self.tokens = tokens
        self.token_counts = token_counts
        self.category_scores = category_scores
        self.evidence_map = evidence_map


class TelegramAudienceAnalyzer:
    def __init__(
        self,
        client_service: TelegramClientService,
        ai_enhancer=None,
        analysis_repository: AudienceAnalysisRepositoryPort | None = None,
    ):
        self._client_service = client_service
        self._ai_enhancer = ai_enhancer
        self._analysis_repository = analysis_repository
        self._lemma_cache: dict[str, str] = {}
        self._morph = MorphAnalyzer()
        self._tokenizer = RegexpTokenizer(r"[A-Za-zА-Яа-яЁё]{4,}")

    async def analyze(
        self,
        source: str,
        message_limit: int = 100,
    ) -> TelegramAudienceReport:
        await self._client_service.ensure_connected()
        client = self._client_service.client

        if not await client.is_user_authorized():
            raise AuthorizationRequiredError("Telegram session is not authorized")

        entity = await self._resolve_entity(source)
        participants_estimate = await self._get_participants_estimate(entity)
        messages = await self._collect_messages(entity, message_limit)
        message_samples = [message.text.strip() for message in messages if message.text.strip()][:20]
        ai_keywords = self._extract_ai_keywords(messages)

        post_topic_profiles = [
            self._analyze_post_topics(message.text, ai_keywords.get(index, []))
            for index, message in enumerate(messages)
        ]
        interest_clusters, category_scores, theme_evidence = self._build_interest_clusters(post_topic_profiles)
        channel_themes = self._build_channel_themes(category_scores, theme_evidence)
        dominant_theme = channel_themes[0] if channel_themes else ChannelTheme(
            key="not_determined",
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
            message_sample_size=len(messages),
        )
        engagement_metrics = self._build_engagement_metrics(messages, participants_estimate)
        audience_persona = self._build_audience_persona(
            source_info,
            interest_clusters,
            dominant_theme,
            messages,
        )
        content_insights = self._build_content_insights(
            dominant_theme=dominant_theme,
            engagement_metrics=engagement_metrics,
        )
        summary = build_summary(
            source_info=source_info,
            interest_clusters=interest_clusters,
        )
        if self._ai_enhancer is None:
            ai_message = "AI-слой не подключен, поэтому портрет аудитории собран локально по контенту канала."
        else:
            ai_message = "Метрики постов собраны. GigaChat достраивает портрет целевой аудитории и рекомендации."

        limitations = [
            "Портрет аудитории строится по содержанию последних постов и метрикам постов, а не по данным профилей подписчиков.",
            "Telegram API не даёт надёжных характеристик подписчиков, поэтому пользовательские эвристики отключены.",
            "Кластеры интересов выводятся по содержанию последних сообщений канала или чата.",
        ]

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
            limitations=limitations,
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

    async def compare_competitors(
        self,
        source: str,
        candidate_sources: list[str],
        message_limit: int = 100,
        top_k: int = 5,
    ) -> CompetitorDiscoveryReport:
        raw_analyzer = TelegramAudienceAnalyzer(self._client_service, ai_enhancer=None)
        base_report = await raw_analyzer.analyze(
            source=source,
            message_limit=message_limit,
        )

        base_normalized = self._normalize_source(source)
        seen_candidates: set[str] = set()
        matches: list[CompetitorMatch] = []
        failures: list[CompetitorFailure] = []

        for candidate_source in candidate_sources:
            normalized_candidate = self._normalize_source(candidate_source)
            if normalized_candidate == base_normalized or normalized_candidate in seen_candidates:
                continue
            seen_candidates.add(normalized_candidate)

            try:
                candidate_report = await raw_analyzer.analyze(
                    source=candidate_source,
                    message_limit=message_limit,
                )
                match = self._build_competitor_match(base_report, candidate_report)
                match = self._enhance_competitor_match_reason(
                    base_report=base_report,
                    candidate_report=candidate_report,
                    match=match,
                )
                matches.append(match)
            except (AuthorizationRequiredError, TelegramOperationError) as exc:
                failures.append(CompetitorFailure(source=candidate_source, error=str(exc)))

        relation_rank = {
            "прямой конкурент": 2,
            "смежный конкурент": 1,
            "широкий рыночный сосед": 0,
        }
        matches = [
            item for item in matches
            if self._should_keep_competitor(item)
        ]
        matches.sort(
            key=lambda item: (relation_rank.get(item.relation_type, -1), item.similarity_score),
            reverse=True,
        )
        return CompetitorDiscoveryReport(
            source=base_report.source,
            competitors=matches[:top_k],
            failed_candidates=failures,
        )

    def _enhance_competitor_match_reason(
        self,
        *,
        base_report: TelegramAudienceReport,
        candidate_report: TelegramAudienceReport,
        match: CompetitorMatch,
    ) -> CompetitorMatch:
        if self._ai_enhancer is None or not hasattr(self._ai_enhancer, "explain_competitor_match"):
            return match

        try:
            reason = self._ai_enhancer.explain_competitor_match(
                base_report=base_report,
                candidate_report=candidate_report,
                match=match,
            )
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
        except Exception as exc:
            logger.warning("GigaChat competitor explanation failed: %s", exc)
            return match
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

    def _persist_analysis(self, report: TelegramAudienceReport) -> None:
        if self._analysis_repository is None:
            return
        try:
            snapshot = build_audience_analysis_snapshot(report)
            self._analysis_repository.save_analysis(snapshot)
        except Exception as exc:
            logger.warning("Audience analysis persistence failed: %s", exc)

    def _build_interest_clusters(
        self,
        post_profiles: list[_PostTopicProfile],
    ) -> tuple[list[AudienceCluster], Counter, dict[str, list[str]]]:
        token_counts = Counter()
        category_counts = Counter()
        evidence_map: dict[str, Counter] = {}
        cluster_tokens: dict[str, list[str]] = {}
        cluster_phrases: dict[str, list[str]] = {}

        for profile in post_profiles:
            token_counts.update(profile.token_counts)
            dominant_category = self._dominant_post_category(profile.category_scores)
            if dominant_category is None:
                continue
            category_counts[dominant_category] += 1
            cluster_tokens.setdefault(dominant_category, []).extend(profile.tokens)
            cluster_phrases.setdefault(
                dominant_category,
                [],
            ).extend(self._extract_dynamic_phrases(profile.tokens))
            dominant_evidence = profile.evidence_map.get(dominant_category, Counter())
            for token, _ in dominant_evidence.most_common(3):
                evidence_map.setdefault(dominant_category, Counter())[token] += 1

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
            dynamic_notes = self._build_dynamic_cluster_notes(
                cluster_tokens.get(key, []),
                cluster_phrases.get(key, []),
                evidence_map.get(key, Counter()),
            )
            clusters.append(
                AudienceCluster(
                    key=key,
                    label=THEME_LABELS.get(key, key),
                    count=count,
                    share=round(count / total, 4),
                    confidence="high" if count >= 6 else "medium" if count >= 3 else "low",
                    notes=dynamic_notes or ["категория выведена по словам из последних постов"],
                )
            )
        return clusters, category_counts, {
            key: self._build_dynamic_cluster_notes(
                cluster_tokens.get(key, []),
                cluster_phrases.get(key, []),
                evidence_map.get(key, Counter()),
            )
            for key in category_counts
        }

    def _analyze_post_topics(self, text: str, keyword_phrases: list[str] | None = None) -> _PostTopicProfile:
        tokens = self._tokenize(text)
        token_counts = FreqDist(tokens)
        category_scores = Counter()
        evidence_map: dict[str, Counter] = {}
        keyword_phrases = keyword_phrases or []

        for token, count in token_counts.items():
            for category, patterns in INTEREST_PATTERNS.items():
                if any(token.startswith(pattern) for pattern in patterns):
                    category_scores[category] += count
                    evidence_map.setdefault(category, Counter())[token] += count

        for phrase in keyword_phrases:
            phrase_tokens = self._tokenize(phrase)
            if not phrase_tokens:
                continue
            for category, patterns in INTEREST_PATTERNS.items():
                if any(
                    token.startswith(pattern)
                    for token in phrase_tokens
                    for pattern in patterns
                ):
                    category_scores[category] += 1.5
                    evidence_map.setdefault(category, Counter())[phrase] += 1

        for category, subtopics in THEME_SUBTOPIC_PATTERNS.items():
            for subtopic, patterns in subtopics.items():
                matched = sum(
                    count
                    for token, count in token_counts.items()
                    if any(token.startswith(pattern) for pattern in patterns)
                )
                if matched == 0:
                    continue
                category_scores[category] += matched * 1.2
                evidence_map.setdefault(category, Counter())[subtopic] += 1

        self._rebalance_close_topics(category_scores, evidence_map, token_counts)

        return _PostTopicProfile(
            tokens=tokens,
            token_counts=token_counts,
            category_scores=category_scores,
            evidence_map=evidence_map,
        )

    @staticmethod
    def _extract_dynamic_phrases(tokens: list[str]) -> list[str]:
        if len(tokens) < 2:
            return []
        phrases: list[str] = []

        bigram_finder = BigramCollocationFinder.from_words(tokens)
        bigram_finder.apply_freq_filter(2)
        bigrams = bigram_finder.nbest(BigramAssocMeasures().raw_freq, 4)
        phrases.extend(" ".join(parts) for parts in bigrams)

        if len(tokens) >= 3:
            trigram_finder = TrigramCollocationFinder.from_words(tokens)
            trigram_finder.apply_freq_filter(2)
            trigrams = trigram_finder.nbest(TrigramAssocMeasures().raw_freq, 3)
            phrases.extend(" ".join(parts) for parts in trigrams)

        return phrases

    def _build_dynamic_cluster_label(
        self,
        key: str,
        tokens: list[str],
        phrases: list[str],
    ) -> str:
        phrase_freq = FreqDist(
            phrase
            for phrase in phrases
            if self._is_meaningful_phrase(phrase)
        )
        if phrase_freq:
            top_phrase = phrase_freq.max()
            return self._humanize_cluster_label(top_phrase)

        token_freq = FreqDist(
            token
            for token in tokens
            if self._is_meaningful_token(token)
        )
        top_tokens = [token for token, _ in token_freq.most_common(2)]
        if top_tokens:
            return self._humanize_cluster_label(" ".join(top_tokens))

        return "Тематический кластер"

    def _build_dynamic_cluster_notes(
        self,
        tokens: list[str],
        phrases: list[str],
        evidence_counter: Counter,
    ) -> list[str]:
        notes: list[str] = []
        phrase_freq = FreqDist(
            phrase
            for phrase in phrases
            if self._is_meaningful_phrase(phrase)
        )
        for phrase, _ in phrase_freq.most_common(3):
            notes.append(phrase)

        if len(notes) < 3:
            for token, _ in evidence_counter.most_common(5):
                if self._is_meaningful_note(token) and token not in notes:
                    notes.append(token)
                if len(notes) >= 5:
                    break

        if len(notes) < 5:
            token_freq = FreqDist(
                token
                for token in tokens
                if self._is_meaningful_token(token)
            )
            for token, _ in token_freq.most_common(5):
                if token not in notes:
                    notes.append(token)
                if len(notes) >= 5:
                    break

        return notes[:5]

    def _deduplicate_dynamic_clusters(
        self,
        clusters: list[AudienceCluster],
    ) -> list[AudienceCluster]:
        deduplicated: list[AudienceCluster] = []
        signatures: list[set[str]] = []

        for cluster in clusters:
            signature = self._cluster_signature(cluster)
            merged = False
            for index, existing_signature in enumerate(signatures):
                overlap = len(signature & existing_signature)
                similarity = overlap / max(len(signature), len(existing_signature), 1)
                if similarity >= 0.6:
                    deduplicated[index] = self._merge_dynamic_clusters(
                        deduplicated[index],
                        cluster,
                    )
                    signatures[index] = self._cluster_signature(deduplicated[index])
                    merged = True
                    break

            if not merged:
                deduplicated.append(cluster)
                signatures.append(signature)

        return deduplicated

    def _cluster_signature(self, cluster: AudienceCluster) -> set[str]:
        parts = [cluster.label, *cluster.notes]
        signature: set[str] = set()
        for part in parts:
            for token in self._tokenize(part):
                if self._is_meaningful_token(token):
                    signature.add(token)
        return signature

    @staticmethod
    def _merge_dynamic_clusters(
        base: AudienceCluster,
        incoming: AudienceCluster,
    ) -> AudienceCluster:
        merged_notes: list[str] = []
        for note in [*base.notes, *incoming.notes]:
            if note not in merged_notes:
                merged_notes.append(note)

        merged_count = base.count + incoming.count
        merged_share = round(base.share + incoming.share, 4)
        confidence_rank = {"low": 0, "medium": 1, "high": 2}
        merged_confidence = base.confidence
        if confidence_rank.get(incoming.confidence, 0) > confidence_rank.get(base.confidence, 0):
            merged_confidence = incoming.confidence

        return AudienceCluster(
            key=base.key,
            label=base.label if len(base.label) >= len(incoming.label) else incoming.label,
            count=merged_count,
            share=merged_share,
            confidence=merged_confidence,
            notes=merged_notes[:5],
        )

    @staticmethod
    def _is_meaningful_token(token: str) -> bool:
        normalized = token.strip().lower()
        return (
            len(normalized) >= 4
            and normalized not in STOPWORDS
            and normalized not in GENERIC_CLUSTER_TOKENS
        )

    def _is_meaningful_phrase(self, phrase: str) -> bool:
        parts = [part for part in phrase.lower().split() if part]
        if len(parts) < 2:
            return False
        meaningful_parts = [part for part in parts if self._is_meaningful_token(part)]
        return len(meaningful_parts) == len(parts)

    def _is_meaningful_note(self, text: str) -> bool:
        normalized = text.strip().lower()
        if " " in normalized:
            return self._is_meaningful_phrase(normalized)
        return self._is_meaningful_token(normalized)

    @staticmethod
    def _humanize_cluster_label(text: str) -> str:
        normalized = re.sub(r"\s+", " ", text.replace("_", " ").strip())
        if not normalized:
            return "Тематический кластер"
        return normalized[:1].upper() + normalized[1:]

    @staticmethod
    def _rebalance_close_topics(
        category_scores: Counter,
        evidence_map: dict[str, Counter],
        token_counts: Counter,
    ) -> None:
        gaming_tokens = {
            "minecraft", "sandbox", "creative", "build", "server", "city", "redstone",
            "survival", "mod", "modpack", "terraria", "stardew",
            "майнкрафт", "сервер", "постройка", "стройка", "выживание", "мод", "сборка",
            "прохождение", "сюжет", "донат", "ивент", "катка",
        }
        esports_tokens = {
            "esports", "dota", "cs2", "valorant", "standoff", "major", "qualifier",
            "playoff", "bracket", "faceit", "hltv", "navi", "spirit", "virtuspro",
            "faze", "mouz", "roster", "lineup", "tournament",
            "киберспорт", "турнир", "мажор", "плейофф", "квал", "квалификация",
            "сетка", "состав", "ростер", "капитан", "рифлер", "эйс",
        }

        gaming_hits = sum(token_counts.get(token, 0) for token in gaming_tokens)
        esports_hits = sum(token_counts.get(token, 0) for token in esports_tokens)

        if gaming_hits and not esports_hits:
            category_scores["gaming"] += gaming_hits * 1.8
            category_scores["sports_esports"] *= 0.6
            evidence_map.setdefault("gaming", Counter())["sandbox and building"] += 1

        if esports_hits and not gaming_hits:
            category_scores["sports_esports"] += esports_hits * 1.8
            evidence_map.setdefault("sports_esports", Counter())["esports tournaments"] += 1

        news_tokens = {
            "breaking", "urgent", "digest", "report", "exclusive", "government",
            "president", "minister", "sanction", "election", "conflict", "diplomat",
            "summit", "parliament", "geopolit",
            "срочно", "сводка", "дайджест", "политика", "правительство", "переговоры",
            "санкция", "выборы", "министр", "президент", "геополитика", "конфликт",
        }
        business_tokens = {
            "startup", "founder", "ceo", "product", "growth", "sales", "enterprise",
            "gmv", "roadmap", "unit", "b2b", "b2c", "manager", "business",
            "бизнес", "продукт", "основатель", "предприниматель", "выручка", "прибыль",
            "юнит", "экономика", "стратегия", "команда", "процесс", "продажи",
        }
        media_tokens = {
            "youtube", "tiktok", "podcast", "creator", "influencer", "music",
            "film", "serial", "show", "beauty", "travel", "style",
            "ютуб", "рилс", "шортс", "подкаст", "блогер", "медиа", "музыка",
            "фильм", "сериал", "шоу", "лайфстайл", "уход", "путешествие",
        }
        humor_tokens = {
            "meme", "joke", "irony", "sarcasm", "satire", "viral", "prank",
            "мем", "мемас", "юмор", "шутка", "ирония", "сарказм", "кринж",
            "прикол", "угар", "жиза", "ору", "ор", "щитпост", "разнос",
        }
        technology_tokens = {
            "python", "backend", "frontend", "api", "sdk", "docker", "postgres",
            "kubernetes", "cloud", "linux", "llm", "openai", "ai", "ml",
            "разработка", "код", "промпт", "нейросеть", "сервер", "архитектура",
            "инфра", "бот", "автоматизация", "данные",
        }
        education_tokens = {
            "course", "lesson", "seminar", "training", "guide", "student",
            "university", "exam", "study", "mentor", "practice", "intern",
            "курс", "урок", "вебинар", "обучение", "студент", "университет",
            "экзамен", "ментор", "стажировка", "навык", "лекция",
        }

        news_hits = sum(token_counts.get(token, 0) for token in news_tokens)
        business_hits = sum(token_counts.get(token, 0) for token in business_tokens)
        media_hits = sum(token_counts.get(token, 0) for token in media_tokens)
        humor_hits = sum(token_counts.get(token, 0) for token in humor_tokens)
        technology_hits = sum(token_counts.get(token, 0) for token in technology_tokens)
        education_hits = sum(token_counts.get(token, 0) for token in education_tokens)

        if news_hits >= 2 and business_hits == 0:
            category_scores["news_current"] += news_hits * 1.5
            category_scores["business"] *= 0.72
            evidence_map.setdefault("news_current", Counter())["breaking news"] += 1
        elif business_hits >= 2 and news_hits == 0:
            category_scores["business"] += business_hits * 1.5
            category_scores["news_current"] *= 0.72
            evidence_map.setdefault("business", Counter())["product growth"] += 1

        if media_hits >= 2 and humor_hits == 0:
            category_scores["media_lifestyle"] += media_hits * 1.4
            category_scores["humor_memes"] *= 0.68
            evidence_map.setdefault("media_lifestyle", Counter())["creator media"] += 1
        elif humor_hits >= 2 and media_hits == 0:
            category_scores["humor_memes"] += humor_hits * 1.4
            category_scores["media_lifestyle"] *= 0.68
            evidence_map.setdefault("humor_memes", Counter())["memes"] += 1

        if technology_hits >= 2 and education_hits == 0:
            category_scores["technology"] += technology_hits * 1.45
            category_scores["education"] *= 0.7
            evidence_map.setdefault("technology", Counter())["software development"] += 1
        elif education_hits >= 2 and technology_hits == 0:
            category_scores["education"] += education_hits * 1.45
            category_scores["technology"] *= 0.7
            evidence_map.setdefault("education", Counter())["courses"] += 1

    def _extract_ai_keywords(self, messages: list[_MessageStats]) -> dict[int, list[str]]:
        if self._ai_enhancer is None or not hasattr(self._ai_enhancer, "extract_post_keywords_batch"):
            return {}
        try:
            limited_messages = messages[:AI_KEYWORD_MESSAGE_LIMIT]
            return self._ai_enhancer.extract_post_keywords_batch([message.text for message in limited_messages])
        except Exception as exc:
            logger.warning("GigaChat keyword extraction failed: %s", exc)
            return {}

    @staticmethod
    def _dominant_post_category(category_scores: Counter) -> str | None:
        if not category_scores:
            return None

        ranked = sorted(
            category_scores.items(),
            key=lambda item: (item[1], item[0] not in GENERIC_THEME_KEYS, item[0]),
            reverse=True,
        )
        return ranked[0][0]

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
        if adjusted.get("media_lifestyle", 0) and adjusted.get("humor_memes", 0):
            adjusted["humor_memes"] += adjusted["media_lifestyle"] * 0.2
        specific_keys = [key for key in adjusted if key not in GENERIC_THEME_KEYS and adjusted.get(key, 0) > 0]
        if specific_keys:
            adjusted["news_current"] *= 0.52
            adjusted["media_lifestyle"] *= 0.74
            adjusted["humor_memes"] *= 0.72

        total = sum(adjusted.values()) or 1
        themes = []
        for key, score in adjusted.most_common():
            if score <= 0:
                continue
            themes.append(
                ChannelTheme(
                    key=translate_key(key),
                    label=THEME_LABELS.get(key, key),
                    share=round(score / total, 4),
                    evidence=theme_evidence.get(key, ["контентный сигнал канала"]),
                )
            )
        return themes

    def _build_audience_persona(
        self,
        source_info: AudienceSource,
        interest_clusters: list[AudienceCluster],
        dominant_theme: ChannelTheme,
        messages: list[_MessageStats],
    ) -> AudiencePersona:
        top_interest = max(interest_clusters, key=lambda cluster: cluster.share) if interest_clusters else None
        posting_density = self._posting_density(messages)
        prime_time_share = self._prime_time_share(messages)

        if prime_time_share >= 0.5:
            activity_pattern = "Аудитория чаще реагирует в вечерние часы и на свежие публикации."
        elif posting_density >= 12:
            activity_pattern = "Аудитория потребляет контент короткими сессиями в течение дня и нормально воспринимает частый постинг."
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
        engagement_metrics: EngagementMetrics,
    ) -> ContentInsights:
        if dominant_theme.label == "новости и актуальная повестка":
            channel_format = "Новостной канал"
        elif dominant_theme.label == "мемы и развлекательный контент":
            channel_format = "Развлекательный канал"
        else:
            channel_format = f"Контентный канал с фокусом на тему '{dominant_theme.label}'"

        if engagement_metrics.deep_engagement_rate >= 0.045:
            strongest_content_hook = "Лучше всего заходят посты, которые хочется переслать дальше и обсудить."
        elif engagement_metrics.view_rate >= 0.25:
            strongest_content_hook = "Лучше всего работает быстрый, легко считываемый контент с сильным заголовком."
        else:
            strongest_content_hook = "Лучше всего срабатывают точечные публикации с понятной пользой для аудитории."

        return ContentInsights(
            channel_format=channel_format,
            strongest_content_hook=strongest_content_hook,
            posting_recommendations=[],
            best_for_growth=[],
        )

    def _tokenize(self, text: str) -> list[str]:
        raw_tokens = self._extract_raw_tokens(text)
        normalized_tokens: list[str] = []
        for raw_token in raw_tokens:
            token = self._lemmatize_token(raw_token)
            if len(token) < 4:
                continue
            if raw_token in STOPWORDS or token in STOPWORDS:
                continue
            normalized_tokens.append(token)
        return normalized_tokens

    def _lemmatize_token(self, token: str) -> str:
        cached = self._lemma_cache.get(token)
        if cached is not None:
            return cached

        if re.fullmatch(r"[а-яё]+", token):
            normalized = self._morph.parse(token)[0].normal_form
        elif re.fullmatch(r"[a-z]+", token):
            normalized = self._normalize_english_token(token)
        else:
            normalized = token

        self._lemma_cache[token] = normalized
        return normalized

    def _extract_raw_tokens(self, text: str) -> list[str]:
        lowered = text.lower()
        return [token for token in self._tokenizer.tokenize(lowered) if token.isalpha()]

    @staticmethod
    def _normalize_english_token(token: str) -> str:
        for suffix in ("ingly", "edly", "ing", "ed", "ies", "es", "s"):
            if len(token) - len(suffix) >= 4 and token.endswith(suffix):
                if suffix == "ies":
                    return token[:-3] + "y"
                return token[:-len(suffix)]
        return token

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

    def _build_competitor_match(
        self,
        base_report: TelegramAudienceReport,
        candidate_report: TelegramAudienceReport,
    ) -> CompetitorMatch:
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
        candidate_dominant_specific_theme = self._dominant_specific_theme_label(candidate_report.channel_themes)
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
            theme_similarity=theme_similarity,
            keyword_similarity=keyword_similarity,
            interest_similarity=interest_similarity,
            audience_similarity=audience_similarity,
            niche_overlap=niche_overlap,
            dominant_theme_bonus=dominant_theme_bonus,
            disqualifiers=disqualifiers,
        )

        reason_parts = [f"Тип: {relation_type}"]
        if matched_themes:
            reason_parts.append(f"Пересекающиеся темы: {', '.join(matched_themes[:3])}")
        if matched_specific_themes:
            reason_parts.append(f"Нишевых общих тем: {shared_specific_theme_count}")
        elif matched_generic_themes:
            reason_parts.append("Совпадение в основном по широким темам")
        if matched_keywords:
            reason_parts.append(f"Общие сигналы контента: {', '.join(matched_keywords[:4])}")
        if interest_similarity >= 0.6:
            reason_parts.append("Похожий набор интересов в контенте")
        if engagement_similarity >= 0.65:
            reason_parts.append("Близкий ритм публикаций и вовлеченность")
        if audience_similarity >= 0.65:
            reason_parts.append("Схожая структура аудитории")
        if disqualifiers:
            reason_parts.append(f"Ограничения: {', '.join(disqualifiers[:3])}")

        return CompetitorMatch(
            source=candidate_report.source,
            similarity_score=round(similarity_score, 4),
            relation_type=relation_type,
            audience_similarity=round(audience_similarity, 4),
            engagement_similarity=round(engagement_similarity, 4),
            format_similarity=round(format_similarity, 4),
            shared_theme_count=shared_theme_count,
            shared_specific_theme_count=shared_specific_theme_count,
            dominant_specific_theme=dominant_specific_theme,
            candidate_dominant_specific_theme=candidate_dominant_specific_theme,
            matched_themes=matched_themes[:5],
            matched_keywords=matched_keywords[:6],
            disqualifiers=disqualifiers,
            reason="; ".join(reason_parts),
        )

    @staticmethod
    def _theme_similarity(
        base_themes: list[ChannelTheme],
        candidate_themes: list[ChannelTheme],
    ) -> tuple[float, list[str], list[str], list[str]]:
        base_ranked = TelegramAudienceAnalyzer._specific_then_generic_themes(base_themes)
        candidate_ranked = TelegramAudienceAnalyzer._specific_then_generic_themes(candidate_themes)
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
        matched_specific_labels = [base_map[key].label for key in overlap_keys if key not in GENERIC_THEME_KEYS]
        matched_generic_labels = [base_map[key].label for key in overlap_keys if key in GENERIC_THEME_KEYS]
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
    def _should_keep_competitor(item: CompetitorMatch) -> bool:
        if item.relation_type in {"прямой конкурент", "смежный конкурент"}:
            return True
        return (
            item.shared_specific_theme_count >= 1
            and item.similarity_score >= 0.3
        )

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
        for index, theme in enumerate(TelegramAudienceAnalyzer._specific_then_generic_themes(base_themes)[:5]):
            theme_weight = 1.0 if index == 0 else 0.7 if index == 1 else 0.45
            if theme.key in GENERIC_THEME_KEYS:
                theme_weight *= 0.4
            for keyword in theme.evidence[:5]:
                normalized = keyword.lower()
                base_weights[normalized] = max(base_weights.get(normalized, 0.0), theme_weight)
        for index, theme in enumerate(TelegramAudienceAnalyzer._specific_then_generic_themes(candidate_themes)[:5]):
            theme_weight = 1.0 if index == 0 else 0.7 if index == 1 else 0.45
            if theme.key in GENERIC_THEME_KEYS:
                theme_weight *= 0.4
            for keyword in theme.evidence[:5]:
                normalized = keyword.lower()
                candidate_weights[normalized] = max(candidate_weights.get(normalized, 0.0), theme_weight)

        if not base_weights or not candidate_weights:
            return 0.0, []
        matched = sorted(set(base_weights) & set(candidate_weights))
        union = set(base_weights) | set(candidate_weights)
        numerator = sum(min(base_weights[key], candidate_weights[key]) for key in matched)
        denominator = sum(max(base_weights.get(key, 0.0), candidate_weights.get(key, 0.0)) for key in union)
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
        overlap = sum(min(base_map.get(key, 0.0), candidate_map.get(key, 0.0)) for key in common_keys)
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
            + closeness(base_metrics.deep_engagement_rate, candidate_metrics.deep_engagement_rate, 0.2)
            + closeness(base_metrics.posts_per_day, candidate_metrics.posts_per_day, 20.0)
        ) / 3

    def _format_similarity(
        self,
        base_content: ContentInsights,
        candidate_content: ContentInsights,
    ) -> float:
        base_tokens = set(self._tokenize(
            f"{base_content.channel_format} {base_content.strongest_content_hook}"
        ))
        candidate_tokens = set(self._tokenize(
            f"{candidate_content.channel_format} {candidate_content.strongest_content_hook}"
        ))
        if not base_tokens or not candidate_tokens:
            return 0.0
        return len(base_tokens & candidate_tokens) / len(base_tokens | candidate_tokens)
