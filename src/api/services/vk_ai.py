from __future__ import annotations

import ast
import json
import re
import time
import uuid
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests
import urllib3
from pydantic import BaseModel, Field

from src.api.config import GigaChatSettings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class VKPostIdea(BaseModel):
    text: str


class VKGeneratedContent(BaseModel):
    content_type: str = Field(default="text")
    text: str
    story_frames: list[str] = Field(default_factory=list)
    image_prompt: str | None = None
    video_script: str | None = None


class VKGroupInsights(BaseModel):
    audience_interests: list[str]
    audience_age: list[str]
    audience_activity: list[str]
    potential_competitors: list[str]
    summary: str
    limitations: list[str]


class GigaChatVKClient:
    def __init__(self, settings: GigaChatSettings):
        self._settings = settings
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def generate_post(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        language: str = "ru",
        length: str = "medium",
        theme: str | None = None,
        tone: str | None = None,
        knowledge_base: str | None = None,
        content_type: str = "text",
    ) -> VKGeneratedContent:
        requested_type = (content_type or "text").strip().lower()
        if requested_type not in {"text", "story", "image", "video"}:
            requested_type = "text"

        schema = VKGeneratedContent.model_json_schema()
        payload = {
            "prompt": prompt,
            "content_type": requested_type,
            "theme": (theme or "").strip() or None,
            "tone": (tone or "").strip() or None,
            "knowledge_base": (knowledge_base or "").strip() or None,
            "context": context or {},
        }
        length_hint = {
            "short": "300-500 characters",
            "medium": "600-900 characters",
            "long": "1000-1500 characters",
        }.get(length, "600-900 characters")
        tone_hint = (tone or "").strip() or "neutral"
        content_rules = {
            "text": "Generate a regular social post.",
            "story": "Generate story content with 3-6 short frames in story_frames and concise text as story caption.",
            "image": "Generate post text + detailed image_prompt describing composition, style, mood, and key objects.",
            "video": "Generate post text + detailed video_script (short scenes, hooks, CTA).",
        }[requested_type]
        full_prompt = (
            "You are a social media editor for VK.\n"
            "Return ONLY valid JSON, no markdown.\n"
            f"Target length: {length_hint}.\n"
            f"Tone of voice: {tone_hint}.\n"
            f"Requested content type: {requested_type}.\n"
            f"{content_rules}\n"
            "Use 2-4 short paragraphs, no hashtags, no emojis, no links.\n"
            f"Write in language: {language}.\n\n"
            f"JSON schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Payload:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        content = self._chat(full_prompt)
        json_text = self._extract_json(content)
        try:
            result = VKGeneratedContent.model_validate_json(json_text)
        except Exception:
            fallback = VKPostIdea.model_validate_json(json_text)
            result = VKGeneratedContent(content_type=requested_type, text=fallback.text)
        result.content_type = requested_type
        result.text = _strip_emojis(result.text or "")
        result.story_frames = [
            _strip_emojis(frame) for frame in (result.story_frames or []) if str(frame or "").strip()
        ][:6]
        if result.image_prompt:
            result.image_prompt = result.image_prompt.strip()
        if result.video_script:
            result.video_script = result.video_script.strip()
        return result

    def generate_image(
        self,
        *,
        prompt: str,
        language: str = "ru",
        theme: str | None = None,
        tone: str | None = None,
        knowledge_base: str | None = None,
    ) -> tuple[bytes, str, str]:
        return self._generate_media_attachment(
            media_type="image",
            prompt=prompt,
            language=language,
            theme=theme,
            tone=tone,
            knowledge_base=knowledge_base,
        )

    def generate_video(
        self,
        *,
        prompt: str,
        language: str = "ru",
        theme: str | None = None,
        tone: str | None = None,
        knowledge_base: str | None = None,
    ) -> tuple[bytes, str, str]:
        return self._generate_media_attachment(
            media_type="video",
            prompt=prompt,
            language=language,
            theme=theme,
            tone=tone,
            knowledge_base=knowledge_base,
        )

    def analyze_group(self, payload: dict[str, Any], language: str = "ru") -> VKGroupInsights:
        schema = VKGroupInsights.model_json_schema()
        compact_payload = self._compact_group_payload(payload)
        full_prompt = (
            "You are a VK community analyst.\n"
            "Use ONLY the supplied data.\n"
            "Return ONLY one JSON object, no markdown, no comments.\n"
            "Do NOT echo the input. Do NOT wrap the response in VKGroupInsights or any other outer key.\n"
            "The top-level JSON object must contain exactly these keys:\n"
            "audience_interests, audience_age, audience_activity, potential_competitors, summary, limitations.\n"
            "Each list item must be a short natural-language bullet, not raw tokens.\n"
            "If some data is missing, mention that in limitations.\n"
            f"Write in language: {language}.\n\n"
            f"JSON schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            "Example response:\n"
            "{\"audience_interests\":[\"Интерес к игровым обновлениям и патчам\"],"
            "\"audience_age\":[\"18-24 - вероятное ядро\"],"
            "\"audience_activity\":[\"Средняя активность\"],"
            "\"potential_competitors\":[\"Паблики про Counter-Strike и киберспорт\"],"
            "\"summary\":\"Короткий вывод.\","
            "\"limitations\":[\"Часть выводов эвристические.\"]}\n\n"
            f"Payload:\n{json.dumps(compact_payload, ensure_ascii=False)}"
        )
        content = self._chat(full_prompt)
        json_text = self._extract_json(content)
        return self._validate_group_insights_json(json_text)

    def _chat(self, prompt: str) -> str:
        payload = {
            "model": self._settings.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        data = self._chat_raw(payload)
        return str(data["choices"][0]["message"]["content"])

    def _chat_raw(self, payload: dict[str, Any]) -> dict[str, Any]:
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            response = requests.post(
                self._settings.base_url,
                headers=headers,
                json=payload,
                verify=self._settings.verify_ssl_certs,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise ValueError(f"GigaChat request failed: {exc}") from exc

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
        cleaned = cleaned.replace("\u00a0", " ").replace("\ufeff", " ")
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("GigaChat did not return JSON")
        cleaned = cleaned[start : end + 1]
        cleaned = re.sub(r"[\x00-\x1F\x7F]", " ", cleaned)
        cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)
        return cleaned

    @staticmethod
    def _validate_group_insights_json(json_text: str) -> VKGroupInsights:
        expected_keys = {
            "audience_interests",
            "audience_age",
            "audience_activity",
            "potential_competitors",
            "summary",
            "limitations",
        }
        try:
            return VKGroupInsights.model_validate_json(json_text)
        except Exception:
            data = None
            try:
                data = json.loads(json_text)
            except Exception:
                repaired = GigaChatVKClient._repair_json_like_text(json_text)
                try:
                    data = json.loads(repaired)
                except Exception:
                    data = ast.literal_eval(repaired)
            if isinstance(data, dict) and "VKGroupInsights" in data and isinstance(data["VKGroupInsights"], dict):
                return VKGroupInsights.model_validate(data["VKGroupInsights"])
            if isinstance(data, dict) and expected_keys.issubset(set(data.keys())):
                return VKGroupInsights.model_validate(data)
            if isinstance(data, dict):
                for value in data.values():
                    if isinstance(value, dict) and expected_keys.issubset(set(value.keys())):
                        return VKGroupInsights.model_validate(value)
            if isinstance(data, dict) and {"group", "metrics", "posts"} & set(data.keys()):
                raise ValueError("GigaChat returned the input payload instead of insights JSON")
            raise

    @staticmethod
    def _repair_json_like_text(text: str) -> str:
        repaired = (text or "").strip()
        repaired = repaired.replace("\u00a0", " ").replace("\ufeff", " ")
        repaired = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)", r'\1"\2"\3', repaired)
        repaired = repaired.replace("'", '"')
        repaired = re.sub(r",\s*([\]}])", r"\1", repaired)
        return repaired

    @staticmethod
    def _compact_group_payload(payload: dict[str, Any]) -> dict[str, Any]:
        group = payload.get("group") or {}
        metrics = payload.get("metrics") or {}
        local_clusters = payload.get("local_clusters") or {}
        posts = payload.get("posts") or []

        compact_posts = []
        for post in posts[:8]:
            if not isinstance(post, dict):
                continue
            compact_posts.append(
                {
                    "text": str(post.get("text") or "")[:320],
                    "likes": int(post.get("likes", 0) or 0),
                    "comments": int(post.get("comments", 0) or 0),
                    "views": int(post.get("views", 0) or 0),
                }
            )

        return {
            "group": {
                "id": group.get("id"),
                "name": group.get("name"),
                "screen_name": group.get("screen_name"),
                "members_count": group.get("members_count"),
                "activity": group.get("activity"),
            },
            "metrics": {
                "average_views": metrics.get("average_views"),
                "average_likes": metrics.get("average_likes"),
                "average_comments": metrics.get("average_comments"),
                "average_reposts": metrics.get("average_reposts"),
                "posts_per_day": metrics.get("posts_per_day"),
                "total_posts_analyzed": metrics.get("total_posts_analyzed"),
                "limitations": metrics.get("limitations", [])[:4],
            },
            "local_clusters": {
                "audience_interests": local_clusters.get("audience_interests", [])[:4],
                "audience_age": local_clusters.get("audience_age", [])[:3],
                "audience_activity": local_clusters.get("audience_activity", [])[:3],
                "potential_competitors": local_clusters.get("potential_competitors", [])[:3],
                "summary": local_clusters.get("summary", ""),
            },
            "posts": compact_posts,
        }

    @staticmethod
    def _extract_attachment_id(payload: dict[str, Any]) -> str | None:
        try:
            message = payload.get("choices", [{}])[0].get("message", {})
        except Exception:
            return None

        attachments = message.get("attachments")
        if isinstance(attachments, list):
            for value in attachments:
                text = str(value or "").strip()
                if text:
                    return text

        content = str(message.get("content") or "")
        match = re.search(r"[A-Za-z0-9_-]{20,}", content)
        if match:
            return match.group(0)
        return None

    def _download_file_content(self, file_id: str) -> tuple[bytes, str]:
        token = self._get_access_token()
        base = self._settings.base_url
        parsed = urlparse(base)
        path = parsed.path
        if "/chat/completions" in path:
            path = path.split("/chat/completions", 1)[0]
        file_url = urlunparse((parsed.scheme, parsed.netloc, f"{path}/files/{file_id}/content", "", "", ""))
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/octet-stream",
        }
        response = requests.get(
            file_url,
            headers=headers,
            verify=self._settings.verify_ssl_certs,
            timeout=60,
        )
        response.raise_for_status()
        mime = response.headers.get("Content-Type", "image/jpeg").split(";")[0].strip() or "image/jpeg"
        return response.content, mime

    def _generate_media_attachment(
        self,
        *,
        media_type: str,
        prompt: str,
        language: str,
        theme: str | None,
        tone: str | None,
        knowledge_base: str | None,
    ) -> tuple[bytes, str, str]:
        user_prompt = (prompt or "").strip()
        if not user_prompt:
            raise ValueError(f"{media_type.capitalize()} prompt is empty")

        media_type = media_type.lower().strip()
        if media_type not in {"image", "video"}:
            raise ValueError("Unsupported media_type")

        tone_hint = (tone or "").strip() or "neutral"
        media_word = "изображение" if media_type == "image" else "видео"
        system_instruction = (
            f"Ты создаешь {media_word} по запросу пользователя. "
            f"Если доступен встроенный инструмент генерации {media_word}, обязательно используй его."
        )
        if theme:
            system_instruction += f" Тема: {theme.strip()}."
        if knowledge_base:
            system_instruction += "\nУчитывай правила из базы знаний:\n" + knowledge_base[:2500]

        payload = {
            "model": self._settings.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {
                    "role": "user",
                    "content": (
                        f"Язык: {language}. Тон: {tone_hint}. "
                        f"Сгенерируй {media_word}: {user_prompt}"
                    ),
                },
            ],
            "temperature": 0.4,
            "function_call": "auto",
        }

        data = self._chat_raw(payload)
        file_id = self._extract_attachment_id(data)
        if not file_id:
            raise ValueError(f"GigaChat did not return {media_type} attachment id")
        file_bytes, mime_type = self._download_file_content(file_id)

        if media_type == "video" and not mime_type.startswith("video/"):
            # Keep fallback for providers returning generic octet-stream
            if mime_type == "application/octet-stream":
                mime_type = "video/mp4"
        if media_type == "image" and not mime_type.startswith("image/"):
            if mime_type == "application/octet-stream":
                mime_type = "image/jpeg"

        return file_bytes, mime_type, file_id


def _strip_emojis(text: str) -> str:
    if not text:
        return text
    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text).strip()
