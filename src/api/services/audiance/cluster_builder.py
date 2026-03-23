from __future__ import annotations

from collections import Counter

from nltk.collocations import (
    BigramAssocMeasures,
    BigramCollocationFinder,
    TrigramAssocMeasures,
    TrigramCollocationFinder,
)
from nltk.probability import FreqDist

from src.api.services.audiance.constants import GENERIC_THEME_KEYS, THEME_LABELS
from src.api.services.audiance.internal_models import PostTopicProfile
from src.api.services.audiance.presenters import translate_key
from src.api.services.audiance.text_processing import AudienceTextProcessor
from src.api.services.dto import AudienceCluster, ChannelTheme


class AudienceClusterBuilder:
    def __init__(self, text_processor: AudienceTextProcessor) -> None:
        self._text_processor = text_processor

    def build_interest_clusters(
        self,
        post_profiles: list[PostTopicProfile],
    ) -> tuple[list[AudienceCluster], Counter[str], dict[str, list[str]]]:
        token_counts = Counter()
        category_counts = Counter()
        evidence_map: dict[str, Counter[str]] = {}
        cluster_tokens: dict[str, list[str]] = {}
        cluster_phrases: dict[str, list[str]] = {}

        for profile in post_profiles:
            token_counts.update(profile.token_counts)
            dominant_category = self._dominant_post_category(profile.category_scores)
            if dominant_category is None:
                continue
            category_counts[dominant_category] += 1
            cluster_tokens.setdefault(dominant_category, []).extend(profile.tokens)
            cluster_phrases.setdefault(dominant_category, []).extend(
                self._extract_dynamic_phrases(profile.tokens)
            )
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

    def build_channel_themes(
        self,
        category_scores: Counter[str],
        theme_evidence: dict[str, list[str]],
    ) -> list[ChannelTheme]:
        if not category_scores:
            return []

        adjusted = Counter(category_scores)
        if adjusted.get("news_current", 0) and adjusted.get("technology", 0):
            adjusted["news_current"] += adjusted["technology"] * 0.35
        if adjusted.get("media_lifestyle", 0) and adjusted.get("humor_memes", 0):
            adjusted["humor_memes"] += adjusted["media_lifestyle"] * 0.2
        specific_keys = [
            key for key in adjusted
            if key not in GENERIC_THEME_KEYS and adjusted.get(key, 0) > 0
        ]
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

    def _build_dynamic_cluster_notes(
        self,
        tokens: list[str],
        phrases: list[str],
        evidence_counter: Counter[str],
    ) -> list[str]:
        notes: list[str] = []
        phrase_freq = FreqDist(
            phrase for phrase in phrases if self._text_processor.is_meaningful_phrase(phrase)
        )
        for phrase, _ in phrase_freq.most_common(3):
            notes.append(phrase)

        if len(notes) < 3:
            for token, _ in evidence_counter.most_common(5):
                if self._text_processor.is_meaningful_note(token) and token not in notes:
                    notes.append(token)
                if len(notes) >= 5:
                    break

        if len(notes) < 5:
            token_freq = FreqDist(
                token for token in tokens if self._text_processor.is_meaningful_token(token)
            )
            for token, _ in token_freq.most_common(5):
                if token not in notes:
                    notes.append(token)
                if len(notes) >= 5:
                    break

        return notes[:5]

    @staticmethod
    def _dominant_post_category(category_scores: Counter[str]) -> str | None:
        if not category_scores:
            return None

        ranked = sorted(
            category_scores.items(),
            key=lambda item: (item[1], item[0] not in GENERIC_THEME_KEYS, item[0]),
            reverse=True,
        )
        return ranked[0][0]
