from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

import requests
import urllib3
from pydantic import BaseModel, Field

from src.api.config import GigaChatSettings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class AITrendLandscapeResponse(BaseModel):
    summary: str
    key_trends: list[str] = Field(default_factory=list)
    infopovody: list[str] = Field(default_factory=list)
    potential_risks: list[str] = Field(default_factory=list)
    company_mentions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class GigaChatTrendsLabeler:
    def __init__(self, settings: GigaChatSettings):
        self._settings = settings
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def analyze_landscape(
        self,
        *,
        articles: list[dict[str, Any]],
        trends: list[dict[str, Any]] | None = None,
        company: str | None = None,
        language: str = "ru",
    ) -> dict[str, Any]:
        if not articles:
            return {
                "summary": "",
                "key_trends": [],
                "infopovody": [],
                "potential_risks": [],
                "company_mentions": [],
                "limitations": ["Нет данных: список публикаций пуст."],
            }

        compact_articles = []
        for item in articles[:30]:
            compact_articles.append(
                {
                    "source": item.get("source"),
                    "title": (item.get("title") or "")[:180],
                    "published_at": item.get("published_at"),
                }
            )
        compact_trends = []
        for item in (trends or [])[:15]:
            compact_trends.append(
                {
                    "term": item.get("term"),
                    "score": round(float(item.get("score") or 0.0), 3),
                    "growth": round(float(item.get("growth") or 0.0), 3),
                }
            )

        schema = AITrendLandscapeResponse.model_json_schema()
        prompt = (
            "Ты аналитик медиатрендов.\n"
            "Задача: кратко выделить тренды и инфоповоды по списку публикаций.\n"
            "Верни ТОЛЬКО валидный JSON без markdown и лишнего текста.\n"
            "Не придумывай факты, которых нет во входных данных.\n"
            f"Язык ответа: {language}.\n"
        )
        if company:
            prompt += f"Отдельно оцени упоминания компании: {company}.\n"
        prompt += (
            f"\nJSON schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Тренд-термы:\n{json.dumps(compact_trends, ensure_ascii=False)}\n\n"
            f"Публикации:\n{json.dumps(compact_articles, ensure_ascii=False)}"
        )

        content = self._chat(prompt)
        json_text = self._extract_json(content)
        parsed = AITrendLandscapeResponse.model_validate_json(json_text)
        return parsed.model_dump()

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
        message = data.get("choices", [{}])[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(part for part in parts if part).strip()
        return str(content or "")

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        raw_key = (self._settings.authorization_key or "").strip()
        if not raw_key:
            raise ValueError("GIGACHAT_AUTH_KEY is not set")

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
            raise ValueError(f"GigaChat OAuth missing access_token: {data}")

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
            raise ValueError("GigaChat did not return JSON")
        cleaned = cleaned[start : end + 1]
        cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)
        return cleaned
