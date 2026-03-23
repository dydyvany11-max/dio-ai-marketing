from __future__ import annotations

import logging

from src.api.config import GigaChatSettings
from src.api.services.audiance.ai_client import GigaChatLLMClient
from src.api.services.audiance.ai_models import AIAudienceInsights, KeywordBatchResult
from src.api.services.audiance.ai_prompts import (
    build_audience_prompt,
    build_competitor_explanation_prompt,
    build_keyword_batch_prompt,
    build_repair_prompt,
)
from src.api.services.audiance.ai_utils import (
    clean_plain_response,
    merge_insights,
    parse_insights,
    safe_snippet,
    truncate_text,
)
from src.api.services.dto import CompetitorMatch, TelegramAudienceReport
from src.api.services.errors import AIEnhancementError

logger = logging.getLogger(__name__)

POST_KEYWORD_BATCH_SIZE = 6
POST_KEYWORD_TEXT_LIMIT = 120


class GigaChatAudienceEnhancer:
    def __init__(self, settings: GigaChatSettings):
        self._client = GigaChatLLMClient(settings)

    def enhance(self, report: TelegramAudienceReport) -> TelegramAudienceReport:
        attempts = [
            build_audience_prompt(report, compact=False),
            build_audience_prompt(report, compact=True),
        ]

        first_error: Exception | None = None
        first_content = ""

        for index, prompt in enumerate(attempts):
            content = self._client.chat_json(prompt)
            if index == 0:
                first_content = content
            try:
                insights = self._parse_insights(content)
                return merge_insights(report, insights)
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
            return merge_insights(report, insights)
        except Exception as exc:
            snippet = safe_snippet(first_content)
            raise AIEnhancementError(
                f"GigaChat returned invalid audience payload. "
                f"First error: {first_error}. Second error: {exc}. "
                f"Response snippet: {snippet}"
            ) from exc

    def validate_connection(self) -> None:
        self._client.chat_plain("Ответь одним коротким словом по-русски: готово.")

    def explain_competitor_match(
        self,
        base_report: TelegramAudienceReport,
        candidate_report: TelegramAudienceReport,
        match: CompetitorMatch,
    ) -> str:
        prompt = build_competitor_explanation_prompt(base_report, candidate_report, match)
        text = clean_plain_response(self._client.chat_plain(prompt))
        if not text:
            raise AIEnhancementError("GigaChat did not return competitor explanation")
        return text

    def extract_post_keywords_batch(self, texts: list[str]) -> dict[int, list[str]]:
        prepared = [
            {
                "index": index,
                "text": truncate_text(text, POST_KEYWORD_TEXT_LIMIT),
            }
            for index, text in enumerate(texts)
            if text and text.strip()
        ]
        if not prepared:
            return {}

        result: dict[int, list[str]] = {}
        for start in range(0, len(prepared), POST_KEYWORD_BATCH_SIZE):
            batch = prepared[start : start + POST_KEYWORD_BATCH_SIZE]
            prompt = build_keyword_batch_prompt(batch)
            try:
                parsed = self._client.chat_structured(prompt, KeywordBatchResult)
            except Exception as exc:
                logger.warning("GigaChat keyword extraction failed: %s", exc)
                continue

            for item in parsed.items:
                cleaned = [
                    truncate_text(keyword, 80)
                    for keyword in item.keywords
                    if keyword.strip()
                ]
                if cleaned:
                    result[item.index] = cleaned[:5]
        return result

    def _repair_response(self, bad_content: str, report: TelegramAudienceReport) -> str:
        prompt = build_repair_prompt(bad_content, report)
        return self._client.chat_json(prompt)

    @staticmethod
    def _parse_insights(content: str) -> AIAudienceInsights:
        return parse_insights(content)
