from __future__ import annotations

import json
import re
from dataclasses import replace

from src.api.services.audiance.ai_models import AIAudienceInsights
from src.api.services.dto import AudiencePersona, ChannelTheme, TelegramAudienceReport
from src.api.services.errors import AIEnhancementError


def parse_insights(content: str) -> AIAudienceInsights:
    return AIAudienceInsights.model_validate_json(extract_json(content))


def extract_json(content: str) -> str:
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


def safe_snippet(content: str, limit: int = 300) -> str:
    return re.sub(r"\s+", " ", (content or "").strip())[:limit]


def clean_plain_response(content: str) -> str:
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


def message_to_text(content: object) -> str:
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


def truncate_text(text: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def merge_insights(report: TelegramAudienceReport, insights: AIAudienceInsights) -> TelegramAudienceReport:
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
