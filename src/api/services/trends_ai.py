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


class AIClusterLabel(BaseModel):
    label: str
    description: str | None = None


class AIClusterResult(BaseModel):
    index: int
    label: str
    description: str | None = None


class AIClusterResponse(BaseModel):
    clusters: list[AIClusterResult]


class GigaChatTrendsLabeler:
    def __init__(self, settings: GigaChatSettings):
        self._settings = settings
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def label_clusters(self, topics: list[dict]) -> list[dict]:
        if not topics:
            return topics
        prompt = self._build_prompt(topics)
        content = self._chat(prompt)
        json_text = self._extract_json(content)
        parsed = AIClusterResponse.model_validate_json(json_text)
        by_index = {item.index: item for item in parsed.clusters}
        labeled = []
        for idx, topic in enumerate(topics):
            item = by_index.get(idx)
            if item:
                topic = dict(topic)
                topic["label"] = item.label
                if item.description:
                    topic["description"] = item.description
            labeled.append(topic)
        return labeled

    def _build_prompt(self, topics: list[dict]) -> str:
        schema = AIClusterResponse.model_json_schema()
        payload = []
        for idx, topic in enumerate(topics):
            payload.append(
                {
                    "index": idx,
                    "size": topic.get("size"),
                    "terms": topic.get("terms", [])[:8],
                    "sample_titles": topic.get("sample_titles", [])[:3],
                }
            )
        return (
            "?? ???????? ????????.\n"
            "??? ???????? ???????? ????? (????????? ????????).\n"
            "???????:\n"
            "1. ????? ?????? JSON ??? markdown.\n"
            "2. ???? ?? ???????.\n"
            "3. ???????? 2-6 ????.\n"
            "4. ?? ????????? ?????.\n\n"
            f"JSON schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"????:\n{json.dumps(payload, ensure_ascii=False)}"
        )

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
