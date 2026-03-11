from __future__ import annotations

import json
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
    ContentInsights,
    TelegramAudienceReport,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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
        prompt = self._build_prompt(report)
        content = self._chat(prompt)
        json_text = self._extract_json(content)
        insights = AIAudienceInsights.model_validate_json(json_text)
        return self._merge(report, insights)

    def validate_connection(self) -> None:
        self._get_access_token()

    def _build_prompt(self, report: TelegramAudienceReport) -> str:
        schema = AIAudienceInsights.model_json_schema()
        payload = self._report_to_payload(report)
        return (
            "Ты анализируешь Telegram-канал или группу.\n"
            "Ниже уже собраны фактические метрики и кластеры. "
            "Твоя задача: построить только смысловую интерпретацию, портрет аудитории, тематику и рекомендации.\n\n"
            "Правила:\n"
            "1. Не выдумывай числовые метрики.\n"
            "2. Опирайся только на переданные данные.\n"
            "3. Верни строго JSON без markdown.\n"
            "4. Пиши на русском языке.\n\n"
            f"JSON schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Данные анализа:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    @staticmethod
    def _report_to_payload(report: TelegramAudienceReport) -> dict[str, Any]:
        return {
            "source": {
                "source": report.source.source,
                "title": report.source.title,
                "entity_id": report.source.entity_id,
                "entity_type": report.source.entity_type,
                "username": report.source.username,
                "participants_estimate": report.source.participants_estimate,
            },
            "activity_clusters": [
                {
                    "label": cluster.label,
                    "count": cluster.count,
                    "share": cluster.share,
                    "confidence": cluster.confidence,
                    "notes": cluster.notes,
                }
                for cluster in report.activity_clusters
            ],
            "age_clusters": [
                {
                    "label": cluster.label,
                    "count": cluster.count,
                    "share": cluster.share,
                    "confidence": cluster.confidence,
                    "notes": cluster.notes,
                }
                for cluster in report.age_clusters
            ],
            "interest_clusters": [
                {
                    "label": cluster.label,
                    "count": cluster.count,
                    "share": cluster.share,
                    "confidence": cluster.confidence,
                    "notes": cluster.notes,
                }
                for cluster in report.interest_clusters
            ],
            "audience_segments": [
                {
                    "label": cluster.label,
                    "count": cluster.count,
                    "share": cluster.share,
                    "confidence": cluster.confidence,
                    "notes": cluster.notes,
                }
                for cluster in report.audience_segments
            ],
            "top_active_segment": {
                "label": report.top_active_segment.label,
                "count": report.top_active_segment.count,
                "share": report.top_active_segment.share,
                "confidence": report.top_active_segment.confidence,
                "notes": report.top_active_segment.notes,
            },
            "dominant_theme": report.dominant_theme.__dict__,
            "channel_themes": [theme.__dict__ for theme in report.channel_themes],
            "engagement_metrics": report.engagement_metrics.__dict__,
            "limitations": report.limitations,
        }

    def _chat(self, prompt: str) -> str:
        token = self._get_access_token()
        payload = {
            "model": self._settings.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
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
            raise ValueError("Не задан GIGACHAT_AUTH_KEY")

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
            raise ValueError(f"GigaChat OAuth не вернул access_token: {data}")

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

    @staticmethod
    def _extract_json(content: str) -> str:
        cleaned = (content or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("GigaChat не вернул JSON")
        cleaned = cleaned[start : end + 1]
        cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)
        return cleaned

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
