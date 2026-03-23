from __future__ import annotations

from collections import Counter

from nltk.probability import FreqDist

from src.api.services.audiance.constants import INTEREST_PATTERNS, THEME_SUBTOPIC_PATTERNS
from src.api.services.audiance.internal_models import MessageStats, PostTopicProfile
from src.api.services.audiance.text_processing import AudienceTextProcessor


class AudienceTopicProfiler:
    def __init__(self, text_processor: AudienceTextProcessor) -> None:
        self._text_processor = text_processor

    def build_post_topic_profiles(
        self,
        messages: list[MessageStats],
        ai_keywords: dict[int, list[str]],
    ) -> list[PostTopicProfile]:
        return [
            self.analyze_post_topics(message.text, ai_keywords.get(index, []))
            for index, message in enumerate(messages)
        ]

    def analyze_post_topics(
        self,
        text: str,
        keyword_phrases: list[str] | None = None,
    ) -> PostTopicProfile:
        tokens = self._text_processor.tokenize(text)
        token_counts = FreqDist(tokens)
        category_scores = Counter()
        evidence_map: dict[str, Counter[str]] = {}
        keyword_phrases = keyword_phrases or []

        for token, count in token_counts.items():
            for category, patterns in INTEREST_PATTERNS.items():
                matched_patterns = [pattern for pattern in patterns if token.startswith(pattern)]
                if not matched_patterns:
                    continue
                weight = max(
                    self._text_processor.language_weight(token, pattern)
                    for pattern in matched_patterns
                )
                category_scores[category] += count * weight
                evidence_map.setdefault(category, Counter())[token] += count * weight

        for phrase in keyword_phrases:
            phrase_tokens = self._text_processor.tokenize(phrase)
            if not phrase_tokens:
                continue
            for category, patterns in INTEREST_PATTERNS.items():
                phrase_weights = [
                    self._text_processor.language_weight(token, pattern)
                    for token in phrase_tokens
                    for pattern in patterns
                    if token.startswith(pattern)
                ]
                if phrase_weights:
                    weight = max(phrase_weights)
                    category_scores[category] += 1.5 * weight
                    evidence_map.setdefault(category, Counter())[phrase] += weight

        for category, subtopics in THEME_SUBTOPIC_PATTERNS.items():
            for subtopic, patterns in subtopics.items():
                matched = sum(
                    count * max(
                        self._text_processor.language_weight(token, pattern)
                        for pattern in patterns
                        if token.startswith(pattern)
                    )
                    for token, count in token_counts.items()
                    if any(token.startswith(pattern) for pattern in patterns)
                )
                if matched == 0:
                    continue
                category_scores[category] += matched * 1.2
                evidence_map.setdefault(category, Counter())[subtopic] += 1

        self._rebalance_close_topics(category_scores, evidence_map, token_counts)

        return PostTopicProfile(
            tokens=tokens,
            token_counts=token_counts,
            category_scores=category_scores,
            evidence_map=evidence_map,
        )

    @staticmethod
    def _rebalance_close_topics(
        category_scores: Counter[str],
        evidence_map: dict[str, Counter[str]],
        token_counts: Counter[str],
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
