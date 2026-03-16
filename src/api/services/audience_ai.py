from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import replace
from typing import Any

import requests
import urllib3
from pydantic import BaseModel, Field

from src.api.config import GigaChatSettings
from src.api.services.dto import (
    AudiencePersona,
    ChannelTheme,
    CompetitorMatch,
    ContentInsights,
    TelegramAudienceReport,
)
from src.api.services.errors import AIEnhancementError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

MAX_MESSAGE_SAMPLES = 8
MAX_MESSAGE_CHARS = 600
MAX_THEME_EVIDENCE = 3
MAX_CLUSTER_NOTES = 3


class AITheme(BaseModel):
    key: str
    label: str
    share: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class AIPersona(BaseModel):
    title: str
    description: str
    motivations: list[str]
    content_preferences: list[str]
    activity_pattern: str


class AIContentInsights(BaseModel):
    channel_format: str
    strongest_content_hook: str
    posting_recommendations: list[str]
    best_for_growth: list[str]


class AIAudienceInsights(BaseModel):
    dominant_theme: AITheme
    channel_themes: list[AITheme]
    audience_persona: AIPersona
    content_insights: AIContentInsights
    summary: str


class GigaChatAudienceEnhancer:
    def __init__(self, settings: GigaChatSettings):
        self._settings = settings
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

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
                    "GigaChat returned non-JSON or invalid JSON on attempt %s: %s",
                    index + 1,
                    exc,
                )

        repaired_content = self._repair_response(first_content, report)
        try:
            insights = self._parse_insights(repaired_content)
            return self._merge(report, insights)
        except Exception as second_error:
            snippet = self._safe_snippet(first_content)
            raise AIEnhancementError(
                f"GigaChat вернул ответ в неподходящем формате. "
                f"Первая ошибка: {first_error}. Вторая ошибка: {second_error}. "
                f"Фрагмент ответа: {snippet}"
            ) from second_error

    def validate_connection(self) -> None:
        self._get_access_token()

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
            "Никакого markdown, списков, дисклеймеров и вводных фраз.\n"
            "Говори просто и понятно для бизнеса.\n"
            "Если канал не прямой конкурент, прямо скажи, чего не хватило.\n\n"
            f"Данные:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        content = self._chat_plain(prompt)
        text = self._clean_plain_response(content)
        if not text:
            raise AIEnhancementError("GigaChat не вернул текстовое объяснение по конкуренту")
        return text

    def _build_prompt(self, report: TelegramAudienceReport, *, compact: bool) -> str:
        payload = self._report_to_payload(report, compact=compact)
        return (
            "Сформируй результат анализа Telegram-канала.\n"
            "Ответ ДОЛЖЕН быть только одним JSON-объектом.\n"
            "Нельзя писать markdown, пояснения, дисклеймеры, вводные фразы и текст до или после JSON.\n"
            "Нельзя писать фразы вроде 'Как и любая языковая модель'.\n"
            "Пиши только на русском языке.\n"
            "Если данных мало, заполни поля осторожно, но JSON все равно верни.\n"
            "Не придумывай числа и характеристики подписчиков, которых нет в данных.\n"
            "Целевую аудиторию выводи только из постов, тем и метрик постов.\n\n"
            "Верни JSON ровно такой структуры:\n"
            "{\n"
            '  "dominant_theme": {"key": "string", "label": "string", "share": 0.0, "evidence": ["string"]},\n'
            '  "channel_themes": [{"key": "string", "label": "string", "share": 0.0, "evidence": ["string"]}],\n'
            '  "audience_persona": {\n'
            '    "title": "string",\n'
            '    "description": "string",\n'
            '    "motivations": ["string"],\n'
            '    "content_preferences": ["string"],\n'
            '    "activity_pattern": "string"\n'
            "  },\n"
            '  "content_insights": {\n'
            '    "channel_format": "string",\n'
            '    "strongest_content_hook": "string",\n'
            '    "posting_recommendations": ["string"],\n'
            '    "best_for_growth": ["string"]\n'
            "  },\n"
            '  "summary": "string"\n'
            "}\n\n"
            f"Данные для анализа:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    def _report_to_payload(self, report: TelegramAudienceReport, *, compact: bool) -> dict[str, Any]:
        message_limit = 5 if compact else MAX_MESSAGE_SAMPLES
        sample_limit = 320 if compact else MAX_MESSAGE_CHARS
        theme_limit = 3 if compact else 5
        cluster_limit = 3 if compact else 5

        return {
            "source": {
                "title": report.source.title,
                "entity_type": report.source.entity_type,
                "username": report.source.username,
                "participants_estimate": report.source.participants_estimate,
                "message_sample_size": report.source.message_sample_size,
            },
            "message_samples": [
                self._truncate_text(text, sample_limit)
                for text in report.message_samples[:message_limit]
                if text.strip()
            ],
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
            "limitations": report.limitations[:2],
        }

    def _chat(self, prompt: str) -> str:
        return self._chat_with_messages(
            [
                {
                    "role": "system",
                    "content": (
                        "Ты возвращаешь только JSON без пояснений, дисклеймеров и markdown. "
                        "Любой ответ вне JSON запрещен."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        )

    def _chat_plain(self, prompt: str) -> str:
        return self._chat_with_messages(
            [
                {
                    "role": "system",
                    "content": (
                        "Ты пишешь кратко, по-русски, без markdown, дисклеймеров и вводных фраз. "
                        "Нужно вернуть только полезный текст ответа."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        )

    def _chat_with_messages(self, messages: list[dict[str, str]]) -> str:
        token = self._get_access_token()
        payload = {
            "model": self._settings.model,
            "messages": messages,
            "temperature": 0.05,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        response = requests.post(
            self._settings.base_url,
            headers=headers,
            json=payload,
            verify=self._settings.verify_ssl_certs,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        raw_key = (self._settings.authorization_key or "").strip()
        if not raw_key:
            raise AIEnhancementError("Не задан GIGACHAT_AUTH_KEY")

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {raw_key.removeprefix('Basic ').strip()}",
        }
        payload = {"scope": self._settings.scope}
        response = requests.post(
            self._settings.auth_url,
            headers=headers,
            data=payload,
            verify=self._settings.verify_ssl_certs,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        token = data.get("access_token")
        if not token:
            raise AIEnhancementError(f"GigaChat OAuth не вернул access_token: {data}")

        expires_at = data.get("expires_at")
        if isinstance(expires_at, (int, float)):
            if expires_at > 10_000_000_000:
                self._token_expires_at = expires_at / 1000 - 60
            else:
                self._token_expires_at = float(expires_at) - 60
        else:
            self._token_expires_at = now + 25 * 60

        self._access_token = token
        return token

    def _repair_response(self, bad_content: str, report: TelegramAudienceReport) -> str:
        payload = self._report_to_payload(report, compact=True)
        repair_prompt = (
            "Нужно вернуть только валидный JSON-объект по данным анализа.\n"
            "Запрещены любые пояснения, markdown и дисклеймеры.\n"
            "Если предыдущий ответ был плохим, игнорируй его содержание и просто верни корректный JSON.\n"
            "Пиши по-русски.\n\n"
            "Структура JSON:\n"
            "{\n"
            '  "dominant_theme": {"key": "string", "label": "string", "share": 0.0, "evidence": ["string"]},\n'
            '  "channel_themes": [{"key": "string", "label": "string", "share": 0.0, "evidence": ["string"]}],\n'
            '  "audience_persona": {"title": "string", "description": "string", "motivations": ["string"], "content_preferences": ["string"], "activity_pattern": "string"},\n'
            '  "content_insights": {"channel_format": "string", "strongest_content_hook": "string", "posting_recommendations": ["string"], "best_for_growth": ["string"]},\n'
            '  "summary": "string"\n'
            "}\n\n"
            f"Данные анализа:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            f"Плохой предыдущий ответ:\n{self._truncate_text(bad_content, 800)}"
        )
        return self._chat(repair_prompt)

    def _parse_insights(self, content: str) -> AIAudienceInsights:
        json_text = self._extract_json(content)
        return AIAudienceInsights.model_validate_json(json_text)

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
            raise ValueError("GigaChat не вернул JSON")

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
            raise ValueError("GigaChat не вернул завершённый JSON-объект")

        candidate = cleaned[start : end + 1]
        candidate = re.sub(r",\s*([\]}])", r"\1", candidate)
        json.loads(candidate)
        return candidate

    @staticmethod
    def _safe_snippet(content: str, limit: int = 300) -> str:
        text = re.sub(r"\s+", " ", (content or "").strip())
        return text[:limit]

    @staticmethod
    def _clean_plain_response(content: str) -> str:
        text = re.sub(r"\s+", " ", (content or "").strip())
        text = re.sub(r"^```(?:text)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        banned_prefixes = (
            "Как и любая языковая модель",
            "Я не могу",
            "Извините",
        )
        for prefix in banned_prefixes:
            if text.startswith(prefix):
                raise AIEnhancementError("GigaChat вернул служебный или бесполезный текст вместо объяснения")
        return text[:500]

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        normalized = re.sub(r"\s+", " ", (text or "").strip())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 1].rstrip() + "…"

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
            motivations=insights.audience_persona.motivations,
            content_preferences=insights.audience_persona.content_preferences,
            activity_pattern=insights.audience_persona.activity_pattern,
        )
        content_insights = ContentInsights(
            channel_format=insights.content_insights.channel_format,
            strongest_content_hook=insights.content_insights.strongest_content_hook,
            posting_recommendations=insights.content_insights.posting_recommendations,
            best_for_growth=insights.content_insights.best_for_growth,
        )
        return replace(
            report,
            ai_enhanced=True,
            ai_message="GigaChat успешно построил портрет аудитории и рекомендации.",
            dominant_theme=dominant_theme,
            channel_themes=channel_themes,
            audience_persona=audience_persona,
            content_insights=content_insights,
            summary=insights.summary,
        )
