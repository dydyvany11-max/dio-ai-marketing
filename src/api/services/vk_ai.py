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
    class Recommendation(BaseModel):
        title: str
        action: str
        rationale: str

    audience_interests: list[str]
    audience_age: list[str]
    audience_activity: list[str]
    potential_competitors: list[str]
    search_tags: list[str] = Field(default_factory=list)
    summary: str
    limitations: list[str]
    recommendations: list[Recommendation] = Field(default_factory=list)


class VKSearchTagsOnly(BaseModel):
    search_tags: list[str] = Field(default_factory=list)


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
            "short": "300-500 символов",
            "medium": "600-900 символов",
            "long": "1000-1500 символов",
        }.get(length, "600-900 символов")
        length_limits = _post_length_rules(length)
        min_chars_hint = length_limits["min_chars"]
        max_chars_hint = length_limits["max_chars"]
        tone_hint = (tone or "").strip() or "нейтральный"
        content_rules = {
            "text": "Сгенерируй обычный пост для соцсети.",
            "story": "Сгенерируй контент для сторис: 3-6 коротких кадров в story_frames и короткий текст-подпись.",
            "image": "Сгенерируй полноценный текст поста и детальный image_prompt (композиция, стиль, настроение, ключевые объекты), строго соответствующий этому тексту.",
            "video": "Сгенерируй текст поста и детальный video_script (сцены, хук, CTA).",
        }[requested_type]
        full_prompt = (
            "Ты редактор контента для ВКонтакте.\n"
            "Верни ТОЛЬКО валидный JSON, без markdown.\n"
            f"Целевая длина: {length_hint}.\n"
            f"Тон: {tone_hint}.\n"
            f"Тип контента: {requested_type}.\n"
            f"{content_rules}\n"
            "Текст должен быть ПОЛНОЦЕННЫМ ГОТОВЫМ ПОСТОМ, а не заголовком/подписью.\n"
            "Структура текста: хук в начале, основная часть с деталями, завершение с понятным выводом или CTA.\n"
            f"Минимальный размер текста: {min_chars_hint} символов.\n"
            f"Жесткий максимум текста: {max_chars_hint} символов, превышать нельзя.\n"
            "Если в запросе пользователя есть конкретные требования (например, добавить анекдот), выполни их явно в тексте.\n"
            "В поле text пиши только итоговый текст поста для публикации.\n"
            "Запрещено писать служебные фразы: 'Написал пост', 'Вот пример текста', 'Заголовок:', 'Текст поста:'.\n"
            "Не объясняй, что ты сделал, и не добавляй комментарии о процессе генерации.\n"
            "Если в контексте есть база знаний, используй ТОЛЬКО фрагменты, которые прямо относятся к теме запроса.\n"
            "Не переноси термины/факты из базы знаний, если их связь с темой неочевидна.\n"
            "Если релевантных фрагментов нет, игнорируй базу знаний и пиши только по запросу пользователя.\n"
            "Используй 2-4 коротких абзаца, без хештегов, без эмодзи, без ссылок.\n"
            f"Язык ответа: {language}.\n\n"
            f"JSON-схема:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Входные данные:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        content = self._chat(full_prompt)
        result: VKGeneratedContent | None = None
        try:
            json_text = self._extract_json(content)
        except Exception:
            json_text = ""
        if json_text:
            result = self._parse_generated_content(json_text, requested_type)
        if result is None:
            repair_prompt = (
                "Исправь предыдущий ответ.\n"
                "Ты вернул JSON не в нужном формате.\n"
                "Верни ТОЛЬКО JSON-объект-экземпляр (не JSON-schema) со строгими ключами:\n"
                "content_type, text, story_frames, image_prompt, video_script.\n"
                f"content_type должен быть: {requested_type}.\n"
                f"Поле text обязательно и должно быть непустой строкой в диапазоне {min_chars_hint}-{max_chars_hint} символов.\n"
                "Поле text должно содержать только финальный текст поста без служебных пояснений и без меток вида 'Заголовок:'/'Текст поста:'.\n"
                f"Язык: {language}.\n"
                f"Повторно входные данные:\n{json.dumps(payload, ensure_ascii=False)}"
            )
            repaired_content = self._chat(repair_prompt)
            try:
                repaired_json = self._extract_json(repaired_content)
            except Exception:
                repaired_json = ""
            if repaired_json:
                result = self._parse_generated_content(repaired_json, requested_type)
            if result is None:
                fallback_text = _normalize_text_for_response(
                    _strip_emojis(repaired_content or content or ""),
                    single_line=True,
                )
                if fallback_text and not fallback_text.startswith("{"):
                    result = VKGeneratedContent(content_type=requested_type, text=fallback_text)
        if result is None:
            raise ValueError("GigaChat returned JSON without required 'text' field")

        if requested_type in {"text", "image", "video"}:
            normalized_preview = _cleanup_generated_post_text(
                _normalize_text_for_response(_strip_emojis(result.text or ""), single_line=True)
            )
            if _is_too_short_post(normalized_preview, length):
                expand_prompt = (
                    "Исправь и расширь предыдущий черновик до полноценного поста.\n"
                    "Верни только валидный JSON-объект с ключами: content_type, text, story_frames, image_prompt, video_script.\n"
                    f"content_type должен быть: {requested_type}.\n"
                    f"text должен быть в диапазоне {min_chars_hint}-{max_chars_hint} символов и содержать хук, основную часть и завершение.\n"
                    "В text не используй служебные фразы и метки ('Написал пост', 'Вот пример текста', 'Заголовок:', 'Текст поста:').\n"
                    "Сохрани смысл исходного запроса пользователя и все явные требования.\n"
                    f"Язык: {language}.\n\n"
                    f"Входные данные:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
                    f"Текущий короткий черновик:\n{json.dumps(result.model_dump(), ensure_ascii=False)}"
                )
                expanded_content = self._chat(expand_prompt)
                try:
                    expanded_json = self._extract_json(expanded_content)
                    expanded_result = self._parse_generated_content(expanded_json, requested_type)
                    if expanded_result is not None:
                        result = expanded_result
                except Exception:
                    pass

        result.content_type = requested_type
        result.text = _cleanup_generated_post_text(
            _normalize_text_for_response(_strip_emojis(result.text or ""), single_line=True)
        )
        if requested_type in {"text", "image", "video"} and _is_too_long_post(result.text, length):
            result.text = _shrink_post_to_max_length(result.text, max_chars_hint)
        result.story_frames = [
            _normalize_text_for_response(_strip_emojis(frame), single_line=True)
            for frame in (result.story_frames or [])
            if str(frame or "").strip()
        ][:6]
        if result.image_prompt:
            result.image_prompt = _normalize_text_for_response(result.image_prompt, single_line=True)
        if result.video_script:
            result.video_script = _normalize_text_for_response(result.video_script, single_line=False)
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

    def build_image_prompt_from_post(
        self,
        *,
        post_text: str,
        language: str = "ru",
        theme: str | None = None,
        tone: str | None = None,
        fallback_prompt: str = "",
    ) -> str:
        normalized_post = _normalize_text_for_response(_strip_emojis(post_text or ""), single_line=True)
        if not normalized_post:
            return (fallback_prompt or "").strip()
        compact_post = normalized_post[:1300]
        tone_hint = (tone or "").strip() or "нейтральный"

        full_prompt = (
            "Ты промпт-инженер для генерации изображений.\n"
            "На входе текст поста для соцсети.\n"
            "Верни только одну строку готового image prompt, без JSON, без markdown, без комментариев.\n"
            "Требования:\n"
            "- не копируй пост дословно;\n"
            "- извлеки визуальную сцену строго из фактов и образов этого поста, без выдуманных сущностей;\n"
            "- опиши композицию, персонажей/объекты, окружение, свет и стиль;\n"
            "- обязательно отрази ключевые элементы текста (компания/контекст, персонажи, действие);\n"
            "- длина 35-80 слов;\n"
            "- без префиксов 'Промпт:' и 'image_prompt:'.\n"
            "- если есть юмористический эпизод, сохрани его визуально, но без карикатурной деградации качества.\n"
            f"Язык: {language}. Тон: {tone_hint}.\n"
            f"Тема: {(theme or '').strip() or 'не задана'}.\n\n"
            f"Текст поста:\n{compact_post}"
        )
        content = self._chat(full_prompt)
        candidate = _normalize_text_for_response(_strip_emojis(content or ""), single_line=True)
        candidate = re.sub(r"(?i)^(image[_\\s-]?prompt|промпт)\\s*:\\s*", "", candidate).strip()
        if not candidate:
            return (fallback_prompt or "").strip()
        words = [w for w in candidate.split() if w.strip()]
        if len(words) < 8:
            return (fallback_prompt or "").strip()
        if len(candidate) > 700:
            candidate = candidate[:700].rsplit(" ", 1)[0].strip()
        return candidate

    def analyze_group(self, payload: dict[str, Any], language: str = "ru") -> VKGroupInsights:
        schema = VKGroupInsights.model_json_schema()
        compact_payload = self._compact_group_payload(payload)
        full_prompt = (
            "Ты аналитик VK-сообществ.\n"
            "Используй только входные данные ниже и верни один валидный JSON-объект без markdown.\n"
            "Не дублируй входной payload и не добавляй внешнюю обертку.\n"
            "Ключи верхнего уровня строго: audience_interests, audience_age, audience_activity, potential_competitors, "
            "search_tags, summary, limitations, recommendations.\n"
            "search_tags: 6-12 коротких тематических тегов/фраз для VK-поиска конкурентов.\n"
            "Важно: в search_tags не включай слишком общие служебные слова; теги должны быть предметными и нишевыми.\n"
            "Используй только тематические термины ниши из описания группы и постов.\n"
            "audience_interests и search_tags формулируй на русском, коротко и по сути ниши; "
            "не используй абстрактные слова без предметного контекста.\n"
            "recommendations: 2-4 объекта с полями title, action, rationale.\n"
            "Все поля и тексты должны быть на русском языке.\n"
            "Если данных мало, явно зафиксируй ограничения в limitations.\n\n"
            f"Язык ответа: {language}.\n\n"
            f"JSON-схема:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Входные данные:\n{json.dumps(compact_payload, ensure_ascii=False)}"
        )
        content = self._chat(full_prompt)
        try:
            json_text = self._extract_json(content)
            return self._validate_group_insights_json(json_text)
        except Exception:
            repair_prompt = (
                "Исправь предыдущий ответ и верни только валидный JSON-объект без markdown.\n"
                "Строгие ключи верхнего уровня: "
                "audience_interests, audience_age, audience_activity, potential_competitors, "
                "search_tags, summary, limitations, recommendations.\n"
                "Никаких дополнительных оберток и комментариев.\n"
                "Все значения должны быть на русском языке.\n\n"
                f"JSON-схема:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
                f"Исходный некорректный ответ:\n{content}"
            )
            repaired = self._chat(repair_prompt)
            repaired_json = self._extract_json(repaired)
            return self._validate_group_insights_json(repaired_json)

    def generate_search_tags_from_group(
        self,
        *,
        group: dict[str, Any],
        language: str = "ru",
        limit: int = 12,
    ) -> list[str]:
        schema = VKSearchTagsOnly.model_json_schema()
        payload = {
            "name": group.get("name"),
            "screen_name": group.get("screen_name"),
            "activity": group.get("activity"),
            "description": group.get("description"),
            "site": group.get("site"),
        }
        full_prompt = (
            "Ты аналитик ниш и конкурентов в VK.\n"
            "На входе только карточка компании/сообщества.\n"
            "Сгенерируй search_tags для поиска ПРЯМЫХ конкурентов.\n"
            "Теги должны отражать нишу, продукт, услугу и предметную область компании.\n"
            "Верни только JSON без markdown.\n"
            "Ключ верхнего уровня строго один: search_tags.\n"
            "search_tags: 6-12 коротких тегов/фраз.\n"
            "Язык тегов: русский.\n\n"
            f"Язык ответа: {language}.\n\n"
            f"JSON-схема:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Входные данные:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        content = self._chat(full_prompt)
        json_text = self._extract_json(content)
        try:
            data = VKSearchTagsOnly.model_validate_json(json_text)
            raw_tags = data.search_tags
        except Exception:
            loaded = self._safe_load_json_like(json_text)
            raw_tags = []
            if isinstance(loaded, dict):
                if isinstance(loaded.get("search_tags"), list):
                    raw_tags = loaded.get("search_tags") or []
                else:
                    for value in loaded.values():
                        if isinstance(value, dict) and isinstance(value.get("search_tags"), list):
                            raw_tags = value.get("search_tags") or []
                            break
        normalized: list[str] = []
        seen: set[str] = set()
        for tag in raw_tags:
            value = " ".join(str(tag or "").split()).strip().lower()
            if not value or value in seen:
                continue
            if len(value.split()) > 5:
                continue
            seen.add(value)
            normalized.append(value)
            if len(normalized) >= max(1, limit):
                break
        return normalized

    def _chat(self, prompt: str) -> str:
        payload = {
            "model": self._settings.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        data = self._chat_raw(payload)
        message = data.get("choices", [{}])[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(part for part in parts if part).strip()
        return str(content or "")

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
    def _parse_generated_content(json_text: str, requested_type: str) -> VKGeneratedContent | None:
        try:
            return VKGeneratedContent.model_validate_json(json_text)
        except Exception:
            pass

        data = GigaChatVKClient._safe_load_json_like(json_text)
        if not isinstance(data, dict):
            return None

        payload = GigaChatVKClient._unwrap_generated_payload(data)
        if not isinstance(payload, dict):
            return None
        if GigaChatVKClient._looks_like_json_schema(payload):
            return None

        text_value = GigaChatVKClient._pick_text_value(payload)
        if not text_value:
            return None

        story_frames_raw = payload.get("story_frames")
        story_frames: list[str] = []
        if isinstance(story_frames_raw, list):
            story_frames = [str(item) for item in story_frames_raw if str(item or "").strip()]

        image_prompt = payload.get("image_prompt")
        if image_prompt is not None:
            image_prompt = str(image_prompt)

        video_script = payload.get("video_script")
        if video_script is not None:
            video_script = str(video_script)

        return VKGeneratedContent(
            content_type=requested_type,
            text=text_value,
            story_frames=story_frames,
            image_prompt=image_prompt,
            video_script=video_script,
        )

    @staticmethod
    def _safe_load_json_like(text: str) -> Any:
        for candidate in (text, GigaChatVKClient._repair_json_like_text(text)):
            try:
                return json.loads(candidate)
            except Exception:
                continue
        try:
            return ast.literal_eval(GigaChatVKClient._repair_json_like_text(text))
        except Exception:
            return None

    @staticmethod
    def _unwrap_generated_payload(data: dict[str, Any]) -> dict[str, Any]:
        current: Any = data
        wrappers = ("VKGeneratedContent", "generated_content", "response", "result", "data", "output")
        for _ in range(3):
            if not isinstance(current, dict):
                break

            unwrapped = False
            for key in wrappers:
                value = current.get(key)
                if isinstance(value, dict):
                    current = value
                    unwrapped = True
                    break
            if unwrapped:
                continue

            if len(current) == 1:
                only_value = next(iter(current.values()))
                if isinstance(only_value, dict):
                    current = only_value
                    continue
            break
        return current if isinstance(current, dict) else data

    @staticmethod
    def _looks_like_json_schema(data: dict[str, Any]) -> bool:
        return isinstance(data.get("properties"), dict) and "text" not in data

    @staticmethod
    def _pick_text_value(data: dict[str, Any]) -> str | None:
        for key in ("text", "content", "message", "caption", "post_text", "post"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _validate_group_insights_json(json_text: str) -> VKGroupInsights:
        expected_keys = {
            "audience_interests",
            "audience_age",
            "audience_activity",
            "potential_competitors",
            "search_tags",
            "summary",
            "limitations",
            "recommendations",
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
                "search_tags": local_clusters.get("search_tags", [])[:8],
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

        tone_hint = (tone or "").strip() or "нейтральный"
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


def _normalize_text_for_response(text: str, *, single_line: bool) -> str:
    value = str(text or "")
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n", value)
    value = re.sub(r"(?i)<p[^>]*>", "", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\\r\\n", "\n").replace("\\n", "\n")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in value.split("\n") if line.strip()]
    if not lines:
        return ""
    if single_line:
        return " ".join(lines)
    return "\n\n".join(lines)


def _cleanup_generated_post_text(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""

    value = value.replace("**", "")

    # Prefer pure post body if model returned editorial wrappers.
    body_marker = re.search(r"(?i)текст\s+поста\s*:\s*", value)
    if body_marker:
        value = value[body_marker.end():].strip()

    value = re.sub(r"(?i)^вот\s+пример\s+текста\s*:\s*", "", value).strip()
    value = re.sub(r"(?i)^пример\s+текста\s*:\s*", "", value).strip()
    value = re.sub(r"(?i)^заголовок\s*:\s*", "", value).strip()
    value = re.sub(r"(?i)^текст\s+поста\s*:\s*", "", value).strip()
    value = re.sub(r"(?i)^написал[аи]?\s+пост[^.!?]*[.!?]\s*", "", value).strip()

    return " ".join(value.split())


def _is_too_short_post(text: str, length: str) -> bool:
    content = (text or "").strip()
    if not content:
        return True
    words = [w for w in content.split() if w.strip()]
    char_count = len(content)
    rule = _post_length_rules(length)
    return char_count < rule["min_chars"] or len(words) < rule["min_words"]


def _is_too_long_post(text: str, length: str) -> bool:
    content = (text or "").strip()
    if not content:
        return False
    rule = _post_length_rules(length)
    return len(content) > rule["max_chars"]


def _post_length_rules(length: str) -> dict[str, int]:
    rules = {
        "short": {"min_chars": 220, "max_chars": 540, "min_words": 35},
        "medium": {"min_chars": 500, "max_chars": 1000, "min_words": 75},
        "long": {"min_chars": 900, "max_chars": 1800, "min_words": 130},
    }
    return rules.get((length or "").strip().lower(), rules["medium"])


def _shrink_post_to_max_length(text: str, max_chars: int) -> str:
    content = " ".join(str(text or "").split()).strip()
    if not content or len(content) <= max_chars:
        return content

    sentences = re.split(r"(?<=[.!?])\s+", content)
    picked: list[str] = []
    total = 0
    for sentence in sentences:
        piece = sentence.strip()
        if not piece:
            continue
        add_len = len(piece) + (1 if picked else 0)
        if total + add_len > max_chars:
            break
        picked.append(piece)
        total += add_len

    if picked:
        trimmed = " ".join(picked).strip()
        if len(trimmed) >= int(max_chars * 0.7):
            return trimmed

    hard_trim = content[:max_chars].rsplit(" ", 1)[0].strip()
    return hard_trim if hard_trim else content[:max_chars].strip()
