from __future__ import annotations

import json
import logging
import re
from dataclasses import replace

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_gigachat.chat_models import GigaChat
from pydantic import BaseModel, Field

from src.api.config import GigaChatSettings
from src.api.services.dto import (
    AudiencePersona,
    ChannelTheme,
    CompetitorMatch,
    TelegramAudienceReport,
)
from src.api.services.errors import AIEnhancementError

logger = logging.getLogger(__name__)

MAX_THEME_EVIDENCE = 1
MAX_CLUSTER_NOTES = 1
POST_KEYWORD_BATCH_SIZE = 6
POST_KEYWORD_TEXT_LIMIT = 120


class AITheme(BaseModel):
    key: str
    label: str
    share: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class AIPersona(BaseModel):
    title: str
    description: str
    age_range: str
    persona_summary: str
    motivations: list[str]
    content_preferences: list[str]
    activity_pattern: str


class AIAudienceInsights(BaseModel):
    dominant_theme: AITheme
    channel_themes: list[AITheme]
    audience_persona: AIPersona
    summary: str


class KeywordItem(BaseModel):
    index: int
    keywords: list[str] = Field(default_factory=list)


class KeywordBatchResult(BaseModel):
    items: list[KeywordItem] = Field(default_factory=list)


class GigaChatAudienceEnhancer:
    def __init__(self, settings: GigaChatSettings):
        credentials = settings.resolved_credentials
        if not credentials:
            raise AIEnhancementError("GigaChat credentials are not configured")

        self._settings = settings
        self._llm = GigaChat(
            credentials=credentials.lstrip("="),
            scope=settings.scope,
            model=settings.model,
            base_url=settings.normalized_base_url,
            auth_url=settings.auth_url,
            verify_ssl_certs=settings.verify_ssl_certs,
            temperature=0.05,
            profanity=False,
        )

    def enhance(self, report: TelegramAudienceReport) -> TelegramAudienceReport:
        attempts = [
            self._build_prompt(report, compact=False),
            self._build_prompt(report, compact=True),
        ]

        first_error: Exception | None = None
        first_content = ""

        for index, prompt in enumerate(attempts):
            content = self._chat(prompt)
            if index == 0:
                first_content = content
            try:
                insights = self._parse_insights(content)
                return self._merge(report, insights)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                logger.warning(
                    "GigaChat returned invalid audience payload on attempt %s: %s",
                    index + 1,
                    exc,
                )

        repaired_content = self._repair_response(first_content, report)
        try:
            insights = self._parse_insights(repaired_content)
            return self._merge(report, insights)
        except Exception as exc:
            snippet = self._safe_snippet(first_content)
            raise AIEnhancementError(
                f"GigaChat returned invalid audience payload. "
                f"First error: {first_error}. Second error: {exc}. "
                f"Response snippet: {snippet}"
            ) from exc

    def validate_connection(self) -> None:
        self._chat_plain("Ответь одним коротким словом по-русски: готово.")

    def explain_competitor_match(
        self,
        base_report: TelegramAudienceReport,
        candidate_report: TelegramAudienceReport,
        match: CompetitorMatch,
    ) -> str:
        payload = {
            "base_channel": {
                "title": base_report.source.title,
                "dominant_theme": base_report.dominant_theme.label,
                "top_topics": [theme.label for theme in base_report.channel_themes[:4]],
            },
            "candidate_channel": {
                "title": candidate_report.source.title,
                "dominant_theme": candidate_report.dominant_theme.label,
                "top_topics": [theme.label for theme in candidate_report.channel_themes[:4]],
            },
            "comparison": {
                "competitor_type": match.relation_type,
                "match_percent": round(match.similarity_score * 100, 1),
                "common_topics": match.matched_themes[:4],
                "common_content_signals": match.matched_keywords[:4],
                "limitations": match.disqualifiers[:3],
            },
        }
        prompt = (
            "Объясни, почему один Telegram-канал похож на другой.\n"
            "Напиши короткое объяснение на русском языке в 1-2 предложениях.\n"
            "Без markdown, списков и дисклеймеров.\n\n"
            f"Данные:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        text = self._clean_plain_response(self._chat_plain(prompt))
        if not text:
            raise AIEnhancementError("GigaChat did not return competitor explanation")
        return text

    def extract_post_keywords_batch(self, texts: list[str]) -> dict[int, list[str]]:
        prepared = [
            {
                "index": index,
                "text": self._truncate_text(text, POST_KEYWORD_TEXT_LIMIT),
            }
            for index, text in enumerate(texts)
            if text and text.strip()
        ]
        if not prepared:
            return {}

        result: dict[int, list[str]] = {}
        for start in range(0, len(prepared), POST_KEYWORD_BATCH_SIZE):
            batch = prepared[start : start + POST_KEYWORD_BATCH_SIZE]
            prompt = (
                "Для каждого Telegram-поста выдели 2-5 коротких ключевых фраз.\n"
                "Ключевые фразы должны быть на русском, если исходный пост на русском.\n"
                "Верни строго JSON с полем items.\n\n"
                f"Посты:\n{json.dumps(batch, ensure_ascii=False)}"
            )
            try:
                parsed = self._chat_structured(prompt, KeywordBatchResult)
            except Exception as exc:
                logger.warning("GigaChat keyword extraction failed: %s", exc)
                continue

            for item in parsed.items:
                cleaned = [
                    self._truncate_text(keyword, 80)
                    for keyword in item.keywords
                    if keyword.strip()
                ]
                if cleaned:
                    result[item.index] = cleaned[:5]
        return result

    def _build_prompt(self, report: TelegramAudienceReport, *, compact: bool) -> str:
        payload = self._report_to_payload(report, compact=compact)
        return (
            "Сформируй результат анализа Telegram-канала.\n"
            "Верни строго один JSON-объект.\n"
            "Все текстовые значения должны быть на русском языке.\n"
            "Нельзя писать markdown, пояснения и текст до или после JSON.\n"
            "Целевую аудиторию выводи только из постов, тем и метрик постов.\n"
            "Не придумывай характеристики подписчиков, которых нет в данных.\n\n"
            "Структура JSON:\n"
            "{\n"
            '  "dominant_theme": {"key": "string", "label": "string", "share": 0.0, "evidence": ["string"]},\n'
            '  "channel_themes": [{"key": "string", "label": "string", "share": 0.0, "evidence": ["string"]}],\n'
            '  "audience_persona": {\n'
            '    "title": "string",\n'
            '    "description": "string",\n'
            '    "age_range": "string",\n'
            '    "persona_summary": "string",\n'
            '    "motivations": ["string"],\n'
            '    "content_preferences": ["string"],\n'
            '    "activity_pattern": "string"\n'
            "  },\n"
            '  "summary": "string"\n'
            "}\n\n"
            f"Данные анализа:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    def _report_to_payload(self, report: TelegramAudienceReport, *, compact: bool) -> dict[str, object]:
        theme_limit = 2 if compact else 3
        cluster_limit = 2 if compact else 3
        return {
            "source": {
                "title": report.source.title,
                "entity_type": report.source.entity_type,
                "username": report.source.username,
                "participants_estimate": report.source.participants_estimate,
                "message_sample_size": report.source.message_sample_size,
            },
            "interest_clusters": [
                {
                    "key": cluster.key,
                    "label": cluster.label,
                    "share": cluster.share,
                    "notes": [
                        self._truncate_text(note, 120)
                        for note in cluster.notes[:MAX_CLUSTER_NOTES]
                    ],
                }
                for cluster in report.interest_clusters[:cluster_limit]
            ],
            "dominant_theme": {
                "key": report.dominant_theme.key,
                "label": report.dominant_theme.label,
                "share": report.dominant_theme.share,
                "evidence": [
                    self._truncate_text(item, 120)
                    for item in report.dominant_theme.evidence[:MAX_THEME_EVIDENCE]
                ],
            },
            "channel_themes": [
                {
                    "key": theme.key,
                    "label": theme.label,
                    "share": theme.share,
                    "evidence": [
                        self._truncate_text(item, 120)
                        for item in theme.evidence[:MAX_THEME_EVIDENCE]
                    ],
                }
                for theme in report.channel_themes[:theme_limit]
            ],
            "engagement_metrics": {
                "average_views": report.engagement_metrics.average_views,
                "average_forwards": report.engagement_metrics.average_forwards,
                "average_reactions": report.engagement_metrics.average_reactions,
                "posts_per_day": report.engagement_metrics.posts_per_day,
            },
            "audience_persona_seed": {
                "title": report.audience_persona.title,
                "description": report.audience_persona.description,
                "age_range": report.audience_persona.age_range,
                "persona_summary": report.audience_persona.persona_summary,
                "activity_pattern": report.audience_persona.activity_pattern,
            },
            "summary_seed": self._truncate_text(report.summary, 180),
            "limitations": report.limitations[:1],
        }

    def _chat(self, prompt: str) -> str:
        response = self._llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Ты возвращаешь только JSON без markdown и пояснений. "
                        "Любой текст вне JSON запрещен. Все текстовые поля должны быть на русском."
                    )
                ),
                HumanMessage(content=prompt),
            ]
        )
        return self._message_to_text(response.content)

    def _chat_plain(self, prompt: str) -> str:
        response = self._llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Ты отвечаешь кратко, по-русски, без markdown, дисклеймеров и вводных фраз. "
                        "Верни только полезный текст ответа."
                    )
                ),
                HumanMessage(content=prompt),
            ]
        )
        return self._message_to_text(response.content)

    def _chat_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        structured_llm = self._llm.with_structured_output(schema, method="format_instructions")
        return structured_llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Возвращай данные строго в указанной структуре. "
                        "Все текстовые поля должны быть на русском, если входные данные на русском."
                    )
                ),
                HumanMessage(content=prompt),
            ]
        )

    def _repair_response(self, bad_content: str, report: TelegramAudienceReport) -> str:
        payload = self._report_to_payload(report, compact=True)
        prompt = (
            "Верни только валидный JSON-объект по данным анализа.\n"
            "Игнорируй невалидный прошлый ответ и пересобери JSON с нуля.\n"
            "Все текстовые поля должны быть на русском.\n\n"
            "Структура JSON:\n"
            "{\n"
            '  "dominant_theme": {"key": "string", "label": "string", "share": 0.0, "evidence": ["string"]},\n'
            '  "channel_themes": [{"key": "string", "label": "string", "share": 0.0, "evidence": ["string"]}],\n'
            '  "audience_persona": {"title": "string", "description": "string", "age_range": "string", "persona_summary": "string", "motivations": ["string"], "content_preferences": ["string"], "activity_pattern": "string"},\n'
            '  "summary": "string"\n'
            "}\n\n"
            f"Данные анализа:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            f"Плохой прошлый ответ:\n{self._truncate_text(bad_content, 800)}"
        )
        return self._chat(prompt)

    def _parse_insights(self, content: str) -> AIAudienceInsights:
        return AIAudienceInsights.model_validate_json(self._extract_json(content))

    @staticmethod
    def _extract_json(content: str) -> str:
        cleaned = (content or "").strip().replace("\ufeff", "")
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            json.loads(cleaned)
            return cleaned
        except Exception:
            pass

        start = cleaned.find("{")
        if start == -1:
            raise ValueError("GigaChat did not return JSON")

        depth = 0
        in_string = False
        escape = False
        end = -1
        for index, char in enumerate(cleaned[start:], start=start):
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index
                    break

        if end == -1:
            raise ValueError("GigaChat did not return a complete JSON object")

        candidate = cleaned[start : end + 1]
        candidate = re.sub(r",\s*([\]}])", r"\1", candidate)
        json.loads(candidate)
        return candidate

    @staticmethod
    def _safe_snippet(content: str, limit: int = 300) -> str:
        return re.sub(r"\s+", " ", (content or "").strip())[:limit]

    @staticmethod
    def _clean_plain_response(content: str) -> str:
        text = re.sub(r"\s+", " ", (content or "").strip())
        text = re.sub(r"^```(?:text)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        banned_prefixes = (
            "As a language model",
            "I cannot",
            "Sorry",
            "Как и любая языковая модель",
            "Я не могу",
            "Извините",
        )
        for prefix in banned_prefixes:
            if text.startswith(prefix):
                raise AIEnhancementError("GigaChat returned boilerplate instead of the requested answer")
        return text[:500]

    @staticmethod
    def _message_to_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
        return str(content)

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        normalized = re.sub(r"\s+", " ", (text or "").strip())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

    @staticmethod
    def _merge(report: TelegramAudienceReport, insights: AIAudienceInsights) -> TelegramAudienceReport:
        dominant_theme = ChannelTheme(
            key=insights.dominant_theme.key,
            label=insights.dominant_theme.label,
            share=insights.dominant_theme.share,
            evidence=insights.dominant_theme.evidence,
        )
        channel_themes = [
            ChannelTheme(
                key=theme.key,
                label=theme.label,
                share=theme.share,
                evidence=theme.evidence,
            )
            for theme in insights.channel_themes
        ]
        audience_persona = AudiencePersona(
            title=insights.audience_persona.title,
            description=insights.audience_persona.description,
            age_range=insights.audience_persona.age_range,
            persona_summary=insights.audience_persona.persona_summary,
            motivations=insights.audience_persona.motivations,
            content_preferences=insights.audience_persona.content_preferences,
            activity_pattern=insights.audience_persona.activity_pattern,
        )
        return replace(
            report,
            ai_enhanced=True,
            ai_message="GigaChat дополнил портрет аудитории по сжатым сигналам канала.",
            dominant_theme=dominant_theme,
            channel_themes=channel_themes,
            audience_persona=audience_persona,
            summary=insights.summary,
        )
