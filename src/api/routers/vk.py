import base64
import json
import logging
import os
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.api.config import (
    PROJECT_ROOT,
    is_gigachat_configured,
    is_yandexgpt_configured,
    load_ai_usage_pricing_settings,
    load_gigachat_settings,
    load_yandexgpt_settings,
)
from src.api.dependencies import get_vk_publisher, get_vk_client
from src.api.schemas import (
    VKAnalyticsRecommendationResponse,
    VKAnalyticsSourceResponse,
    VKAIPostRequest,
    VKAIPostResponse,
    VKAudienceProfileResponse,
    VKCompetitorFoundResponse,
    VKGroupAIInsights,
    VKGroupAnalyzeRequest,
    VKGroupAnalyzeHistoryClearResponse,
    VKGroupAnalyzeHistoryDeleteItemResponse,
    VKGroupAnalyzeHistoryItemResponse,
    VKGroupAnalyzeHistoryListResponse,
    VKGroupAnalyzeResponse,
    VKGroupMetricsResponse,
    VKRecommendationsChatRequest,
    VKRecommendationsChatResponse,
    VKRecommendationsChatMessage,
    VKAIUsageResponse,
    VKPostGenerateHistoryClearResponse,
    VKPostGenerateHistoryDeleteItemResponse,
    VKPostGenerateHistoryItemResponse,
    VKPostGenerateHistoryListResponse,
    VKPublishRequest,
    VKPublishResponse,
    VKRegenerateImageRequest,
    VKRegenerateImageResponse,
    VKRAGChunkUsedResponse,
)
from src.api.services.errors import VKAuthorizationError, VKOperationError
from src.api.services.vk_analysis_helpers import (
    _build_audience_profile,
    _extract_ai_search_tags,
    _extract_ai_topic_labels,
    _finalize_search_tags_for_vk_ru,
    _filter_tags_by_group_context,
    _is_query_term,
    _is_query_word,
    _tokenize_loose,
    _is_group_auth_restriction,
    _render_group_report_png,
    _search_vk_competitors as _search_vk_competitors_impl,
)
from src.api.services.vk_analysis_history import (
    append_analysis_chat_messages,
    clear_analysis_history,
    delete_analysis_history_item,
    get_analysis_history_item,
    list_analysis_history,
    save_analysis_report,
)
from src.api.services.vk_ai import GigaChatVKClient, YandexGPTVKClient
from src.api.services.vk_client import VKClient
from src.api.services.vk_content_history import (
    clear_generated_posts_history,
    delete_generated_post,
    get_generated_post,
    list_generated_posts,
    save_generated_post,
)
from src.api.services.vk_knowledge import VKKnowledgeStore
from src.api.services.vk_local_analysis import build_local_vk_insights_with_context
from src.api.services.vk_public import (
    fetch_public_group_data,
    has_vk_browser_profile,
    launch_vk_browser_login,
    search_public_groups,
    vk_browser_profile_dir,
)
from src.api.services.vk_publisher import VKPublisher, VKPublishRequest as VKPublishPayload

router = APIRouter(prefix="/vk", tags=["VK"])
_knowledge_store = VKKnowledgeStore()
# Use uvicorn logger so trace messages are visible in backend console by default.
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)

_VK_TOKEN_PATH = Path(os.getenv("VK_TOKEN_PATH", str(PROJECT_ROOT / "vk_token.json")))


def _load_vk_token() -> str | None:
    if not _VK_TOKEN_PATH.exists():
        return None
    try:
        data = json.loads(_VK_TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    token = data.get("access_token")
    return token if isinstance(token, str) and token.strip() else None


def _load_group_token() -> str | None:
    token = os.getenv("VK_GROUP_TOKEN", "").strip()
    return token or None


def _resolve_access_token(payload_token: str | None = None) -> str | None:
    return payload_token or _load_group_token() or _load_vk_token()


def _resolve_access_tokens(payload_token: str | None = None) -> list[str]:
    tokens: list[str] = []
    for token in [payload_token, _load_group_token(), _load_vk_token()]:
        value = (token or "").strip()
        if value and value not in tokens:
            tokens.append(value)
    return tokens


def _requested_ai_provider(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"gigachat", "yandex", "auto"}:
        return normalized
    return "auto"


def _default_ai_provider() -> str:
    configured = str(os.getenv("VK_AI_PROVIDER", "auto") or "auto").strip().lower()
    if configured in {"gigachat", "yandex"}:
        return configured
    return "auto"


def _resolve_ai_provider(requested: str | None = None) -> str:
    provider = _requested_ai_provider(requested)
    if provider == "auto":
        provider = _default_ai_provider()
    if provider == "auto":
        if is_gigachat_configured():
            return "gigachat"
        if is_yandexgpt_configured():
            return "yandex"
        return "none"
    return provider


def _build_text_ai_client(requested_provider: str | None = None):
    provider = _resolve_ai_provider(requested_provider)
    if provider == "yandex":
        settings = load_yandexgpt_settings()
        client = YandexGPTVKClient(settings)
        return client, provider, client.model_name(), client.auth_mode()
    if provider == "gigachat":
        settings = load_gigachat_settings()
        client = GigaChatVKClient(settings)
        return client, provider, client.model_name(), client.auth_mode()
    raise RuntimeError("No AI provider configured. Set GigaChat or YandexGPT credentials in .env")


def _build_media_ai_client(preferred_provider: str):
    if preferred_provider == "gigachat" and is_gigachat_configured():
        settings = load_gigachat_settings()
        return GigaChatVKClient(settings)
    if preferred_provider == "yandex" and is_gigachat_configured():
        # Yandex text models do not generate binary media; use GigaChat as media backend.
        settings = load_gigachat_settings()
        return GigaChatVKClient(settings)
    return None


def _call_with_retries(
    func,
    *,
    attempts: int = 3,
    base_delay_sec: float = 0.8,
    retry_exceptions: tuple[type[Exception], ...] = (Exception,),
):
    last_error: Exception | None = None
    attempts = max(1, int(attempts or 1))
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except retry_exceptions as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = min(base_delay_sec * (2 ** (attempt - 1)), 5.0)
            try:
                import time

                time.sleep(delay)
            except Exception:
                pass
    if last_error is not None:
        raise last_error
    raise RuntimeError("Retry call failed without explicit exception")


def _search_vk_competitors(*args, **kwargs):
    kwargs.setdefault("public_search_fn", search_public_groups)
    kwargs.setdefault("public_group_fetch_fn", fetch_public_group_data)
    return _search_vk_competitors_impl(*args, **kwargs)


def _build_kb_chunks_payload(kb_snippets: list[dict]) -> list[VKRAGChunkUsedResponse]:
    payload: list[VKRAGChunkUsedResponse] = []
    for item in kb_snippets or []:
        snippet = str(item.get("snippet") or "").strip()
        snippet_preview = snippet[:220].strip() if snippet else None
        explain = item.get("relevance_explain") or {}
        token_overlap = int(explain.get("token_overlap") or 0)
        phrase_hits = int(explain.get("phrase_hits") or 0)
        raw_term_hits = int(explain.get("raw_term_hits") or 0)
        reason_parts = []
        if token_overlap:
            reason_parts.append(f"token overlap: {token_overlap}")
        if phrase_hits:
            reason_parts.append(f"phrase hits: {phrase_hits}")
        if raw_term_hits:
            reason_parts.append(f"exact term hits: {raw_term_hits}")
        reason = ", ".join(reason_parts) if reason_parts else "high relevance score"
        payload.append(
            VKRAGChunkUsedResponse(
                title=(str(item.get("title") or "").strip() or None),
                filename=(str(item.get("filename") or "").strip() or None),
                source_type=(str(item.get("source_type") or "").strip() or None),
                score=float(item.get("score") or 0.0),
                reason=reason,
                matched_terms=[str(term) for term in (item.get("matched_terms") or []) if str(term).strip()],
                snippet_preview=snippet_preview,
            )
        )
    return payload


def _json_for_log(payload: object, *, max_chars: int = 120000) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    full = str(os.getenv("VK_AI_TRACE_FULL", "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
    if full or len(text) <= max_chars:
        return text
    return (
        text[:max_chars].rstrip()
        + f"\n...<trimmed: {len(text) - max_chars} chars omitted, set VK_AI_TRACE_FULL=1 for full dump>"
    )


def _build_ai_usage_payload(*clients: object) -> VKAIUsageResponse | None:
    usage_entries: list[dict] = []
    for client in clients:
        if client is None:
            continue
        get_usage = getattr(client, "get_usage_totals", None)
        if not callable(get_usage):
            continue
        usage = get_usage() or {}
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0)
        if input_tokens <= 0 and output_tokens <= 0 and total_tokens <= 0:
            continue
        usage_entries.append(
            {
                "provider": str(getattr(client, "provider_name", lambda: "unknown")() or "unknown"),
                "model": str(getattr(client, "model_name", lambda: "")() or "") or None,
                "input_tokens": max(0, input_tokens),
                "output_tokens": max(0, output_tokens),
                "total_tokens": max(0, total_tokens),
            }
        )

    if not usage_entries:
        return None

    total_input = sum(item["input_tokens"] for item in usage_entries)
    total_output = sum(item["output_tokens"] for item in usage_entries)
    total_tokens = sum(item["total_tokens"] for item in usage_entries)

    provider = usage_entries[0]["provider"] if len(usage_entries) == 1 else "mixed"
    model_values = [item["model"] for item in usage_entries if item["model"]]
    model = model_values[0] if len(model_values) == 1 else ", ".join(sorted(set(model_values))) or None

    pricing = load_ai_usage_pricing_settings()
    cost_acc = 0.0
    any_price = False
    for item in usage_entries:
        in_rate, out_rate = pricing.rates_for(item["provider"])
        if in_rate <= 0 and out_rate <= 0:
            continue
        any_price = True
        cost_acc += (item["input_tokens"] / 1000.0) * in_rate
        cost_acc += (item["output_tokens"] / 1000.0) * out_rate

    estimated_cost = round(cost_acc, 6) if any_price else None
    currency = pricing.currency if any_price else None

    return VKAIUsageResponse(
        provider=provider,
        model=model,
        input_tokens=total_input,
        output_tokens=total_output,
        total_tokens=total_tokens,
        estimated_cost=estimated_cost,
        currency=currency,
    )


def _normalize_source(source: str) -> str:
    value = source.strip()
    if value.startswith("https://") or value.startswith("http://"):
        value = value.split("vk.com/")[-1].strip("/")
    if "/" in value:
        value = value.split("/", 1)[0]
    if "?" in value:
        value = value.split("?", 1)[0]
    if "#" in value:
        value = value.split("#", 1)[0]
    wall_match = re.search(r"wall-?(\d+)", value, flags=re.IGNORECASE)
    if wall_match:
        value = wall_match.group(1)
    if value.startswith("public"):
        value = value.replace("public", "")
    if value.startswith("club"):
        value = value.replace("club", "")
    if value.startswith("@"):
        value = value[1:]
    return value


def _resolve_group_identity(source: str) -> tuple[str, int | None]:
    normalized = _normalize_source(source)
    if normalized.isdigit():
        return normalized, int(normalized)
    return normalized, None


def _default_group_id() -> int | None:
    raw = os.getenv("VK_GROUP_ID", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _avg(values: list[int]) -> int:
    if not values:
        return 0
    return int(sum(values) / len(values))


def _posts_per_day(dates: list[int]) -> float:
    if len(dates) < 2:
        return 0.0
    dates_sorted = sorted(date for date in dates if date > 0)
    if len(dates_sorted) < 2:
        return 0.0
    unique_days = {datetime.fromtimestamp(date).date() for date in dates_sorted}
    span_seconds = max(0, dates_sorted[-1] - dates_sorted[0])
    span_days = max(len(unique_days), int(span_seconds // 86400) + 1, 1)
    return round(len(dates_sorted) / span_days, 3)


def _public_post_id_to_int(post_id: str) -> int:
    value = (post_id or "").rsplit("_", 1)[-1]
    try:
        return int(value)
    except ValueError:
        return 0


def _public_post_owner_to_group_id(post_id: str) -> int | None:
    value = str(post_id or "").strip()
    if not value or "_" not in value:
        return None
    owner = value.split("_", 1)[0].strip()
    if not owner:
        return None
    try:
        owner_id = int(owner)
    except ValueError:
        return None
    return abs(owner_id) if owner_id else None


def _build_payload_from_public_group(public_group) -> tuple[list[dict], list[int], list[int], list[int], list[int], list[int], list[dict]]:
    posts = [
        {
            "text": item.text[:1200],
            "views": int(item.views or 0),
            "likes": int(item.likes or 0),
            "comments": int(item.comments or 0),
            "reposts": int(item.reposts or 0),
            "date": int(item.timestamp or 0),
        }
        for item in (public_group.posts or [])
    ]
    metrics_views = [item["views"] for item in posts if 10 <= item["views"] <= 50_000_000]
    metrics_likes = [item["likes"] for item in posts if item["likes"] > 0]
    metrics_comments = [item["comments"] for item in posts if item["comments"] > 0]
    metrics_reposts = [item["reposts"] for item in posts if item["reposts"] > 0]
    post_dates = [item["date"] for item in posts if item["date"] > 0]
    top_posts = [
        {
            "post_id": _public_post_id_to_int(item.post_id),
            "date": int(item.timestamp or 0),
            "views": int(item.views or 0),
            "likes": int(item.likes or 0),
            "comments": int(item.comments or 0),
            "reposts": int(item.reposts or 0),
        }
        for item in (public_group.posts or [])
    ]
    return posts, metrics_views, metrics_likes, metrics_comments, metrics_reposts, post_dates, top_posts


def _is_sparse_post_content(posts: list[dict], *, min_posts: int = 6, min_text_chars: int = 120) -> bool:
    if not posts:
        return True
    if len(posts) < min_posts:
        return True

    non_empty_texts = [str(item.get("text") or "").strip() for item in posts if str(item.get("text") or "").strip()]
    if not non_empty_texts:
        return True

    avg_chars = sum(len(text) for text in non_empty_texts) / max(len(non_empty_texts), 1)
    long_text_posts = sum(1 for text in non_empty_texts if len(text) >= min_text_chars)
    return avg_chars < min_text_chars or long_text_posts < max(2, len(posts) // 5)


def _is_bad_public_group_name(name: str | None) -> bool:
    value = " ".join(str(name or "").split()).strip().lower()
    if not value:
        return True
    bad_values = {
        "error",
        "vk",
        "profile",
        "login",
        "access denied",
        "restricted access",
    }
    return (
        value in bad_values
        or value.startswith("error")
        or value.startswith("\u043e\u0448\u0438\u0431\u043a\u0430")
        or "not a robot" in value
        or "access denied" in value
        or "restricted" in value
        or "\u043d\u0435 \u0440\u043e\u0431\u043e\u0442" in value
        or "\u0434\u043e\u0441\u0442\u0443\u043f \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d" in value
    )


def _normalize_ai_russian_list(values: list[str] | None, *, fallback: list[str] | None = None) -> list[str]:
    mapping = {
        "food": "\u043f\u0440\u043e\u0434\u0443\u043a\u0442\u044b \u043f\u0438\u0442\u0430\u043d\u0438\u044f",
        "drink": "\u043d\u0430\u043f\u0438\u0442\u043a\u0438",
        "drinks": "\u043d\u0430\u043f\u0438\u0442\u043a\u0438",
        "business": "\u0431\u0438\u0437\u043d\u0435\u0441",
        "services": "\u0443\u0441\u043b\u0443\u0433\u0438",
        "retail": "\u0440\u0438\u0442\u0435\u0439\u043b",
        "store": "\u043c\u0430\u0433\u0430\u0437\u0438\u043d\u044b",
        "stores": "\u043c\u0430\u0433\u0430\u0437\u0438\u043d\u044b",
    }
    stop = {
        "\u043d\u0430\u0448\u0438",
        "\u0432\u0430\u0448\u0438",
        "\u043f\u0440\u0438\u0432\u0435\u0442",
        "\u043b\u0430\u0439\u043a\u0438",
        "\u043c\u0435\u043c\u044b",
        "\u043a\u043e\u043d\u0442\u0435\u043d\u0442",
        "our",
        "your",
        "hello",
        "likes",
        "memes",
        "content",
    }
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = " ".join(str(raw or "").split()).strip().lower()
        if not value:
            continue
        value = mapping.get(value, value)
        value = value.replace("_", " ").replace("-", " ").strip()
        if value in stop or len(value) < 3:
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    if not out and fallback:
        for raw in fallback:
            value = " ".join(str(raw or "").split()).strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)
            if len(out) >= 4:
                break
    return out[:6]


def _summary_looks_bad(summary: str) -> bool:
    value = " ".join(str(summary or "").split()).strip().lower()
    if not value:
        return True
    if value.startswith("error") or value.startswith("\u043e\u0448\u0438\u0431\u043a\u0430"):
        return True
    if "error" in value:
        return True
    if "\u043e\u0448\u0438\u0431\u043a\u0430" in value:
        return True
    if "audience" in value and ("18-" in value or "years" in value):
        return True
    if "\u0430\u0443\u0434\u0438\u0442\u043e\u0440" in value and ("\u043b\u0435\u0442" in value or "18-" in value):
        return True
    return False


def _build_group_level_summary(
    *,
    group_name: str,
    screen_name: str | None = None,
    group_activity: str | None,
    group_description: str | None,
    tags: list[str],
    posts_analyzed: int,
) -> str:
    cleaned_name = " ".join(str(group_name or "").split()).strip()
    if _is_bad_public_group_name(cleaned_name):
        cleaned_name = (screen_name or "\u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u043e").strip()
    niche = ", ".join(tags[:3]) if tags else "\u043e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u043a\u043e\u043d\u0442\u0435\u043d\u0442 \u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u0430"
    activity = str(group_activity or "").strip() or "\u0431\u0435\u0437 \u044f\u0432\u043d\u043e\u0439 \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0438"
    has_description = bool(str(group_description or "").strip())
    description_note = (
        "\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u0430 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d\u043e."
        if has_description
        else "\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u0430 \u043a\u0440\u0430\u0442\u043a\u043e\u0435."
    )
    posts_note = (
        f"\u0412 \u0430\u043d\u0430\u043b\u0438\u0437\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043e {int(posts_analyzed or 0)} \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0439."
        if int(posts_analyzed or 0) > 0
        else "\u041f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b, \u0432\u044b\u0432\u043e\u0434 \u0441\u0434\u0435\u043b\u0430\u043d \u043f\u043e \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u044e \u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u0430."
    )
    return (
        f"\u0413\u0440\u0443\u043f\u043f\u0430 \u00ab{cleaned_name}\u00bb \u043e\u0442\u043d\u043e\u0441\u0438\u0442\u0441\u044f \u043a \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0438 \u00ab{activity}\u00bb \u0438 \u0432\u0435\u0434\u0451\u0442 \u043a\u043e\u043d\u0442\u0435\u043d\u0442 \u0432 \u0442\u0435\u043c\u0430\u0445: {niche}. "
        f"{posts_note} {description_note}"
    )


def _build_image_prompt_from_generated_text(
    *,
    generated_text: str,
    fallback_prompt: str,
    theme: str | None,
    tone: str | None,
    ai_image_prompt: str | None,
) -> str:
    # Compact fallback if AI image-prompt builder is unavailable.
    # We still derive this from generated post text, but keep it concise.
    text = (generated_text or "").strip()
    if text:
        compact = " ".join(text.split())
        sentences = re.split(r"(?<=[.!?])\s+", compact)
        core = " ".join(sentences[:2]).strip()[:360]
        parts = [f"Сцена по мотивам поста: {core}"]
        if theme and str(theme).strip():
            parts.append(f"Тема: {str(theme).strip()}")
        if tone and str(tone).strip():
            parts.append(f"Тон: {str(tone).strip()}")
        if ai_image_prompt and str(ai_image_prompt).strip():
            parts.append(f"Доп.детали: {str(ai_image_prompt).strip()[:220]}")
        return ". ".join(parts)
    if ai_image_prompt and str(ai_image_prompt).strip():
        return str(ai_image_prompt).strip()
    return (fallback_prompt or "").strip()


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _safe_save_generated_history(*, request_payload: dict, response_payload: dict) -> int | None:
    try:
        return save_generated_post(
            request_payload=request_payload,
            response_payload=response_payload,
        )
    except Exception:
        return None


def _safe_save_analysis_history(*, source_input: str, post_limit: int, language: str, report: dict) -> int | None:
    try:
        return save_analysis_report(
            source_input=source_input,
            post_limit=post_limit,
            language=language,
            report=report,
        )
    except Exception:
        return None


def _normalize_chat_messages(messages: list[dict] | None, limit: int = 120) -> list[dict]:
    def _normalize_chat_text(value: object) -> str:
        raw = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
        lines: list[str] = []
        for line in raw.split("\n"):
            lines.append(" ".join(line.split()).strip())
        compact_lines: list[str] = []
        previous_blank = False
        for line in lines:
            if line:
                compact_lines.append(line)
                previous_blank = False
            elif not previous_blank:
                compact_lines.append("")
                previous_blank = True
        return "\n".join(compact_lines).strip()

    normalized: list[dict] = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        text = _normalize_chat_text(item.get("text"))
        if not text:
            continue
        normalized.append(
            {
                "role": role,
                "text": text[:5000],
                "created_at": str(item.get("created_at") or _utc_now_iso()),
            }
        )
    return normalized[-max(1, min(limit, 200)) :]


def _coerce_post_report(history_item: dict) -> VKAIPostResponse:
    report = history_item.get("report") if isinstance(history_item.get("report"), dict) else {}
    payload = dict(report)
    base_text = str(payload.get("text") or history_item.get("text_preview") or history_item.get("prompt") or "").strip()
    char_count = int(payload.get("char_count") or history_item.get("char_count") or len(base_text))
    word_count = int(payload.get("word_count") or history_item.get("word_count") or len([w for w in base_text.split() if w.strip()]))

    payload.setdefault("text", base_text)
    payload.setdefault("content_type", history_item.get("content_type") or "text")
    payload.setdefault("published", bool(payload.get("published") if "published" in payload else history_item.get("published")))
    payload.setdefault("post_id", history_item.get("post_id"))
    payload.setdefault("owner_id", history_item.get("owner_id"))
    payload.setdefault("media_attached", None)
    payload.setdefault("publish_note", None)
    payload.setdefault("char_count", max(0, char_count))
    payload.setdefault("word_count", max(0, word_count))
    payload.setdefault("token_estimate", max(1, int(payload.get("token_estimate") or round(max(0, char_count) / 4) or 1)))
    payload.setdefault("token_estimate_method", str(payload.get("token_estimate_method") or "chars/4"))
    payload.setdefault("theme", history_item.get("theme"))
    payload.setdefault("tone", history_item.get("tone"))
    payload.setdefault("story_frames", payload.get("story_frames") or [])
    payload.setdefault("image_prompt", payload.get("image_prompt"))
    payload.setdefault("video_script", payload.get("video_script"))
    payload.setdefault("generated_image_base64", payload.get("generated_image_base64"))
    payload.setdefault("generated_image_mime_type", payload.get("generated_image_mime_type"))
    payload.setdefault("image_reference_files_attached", int(payload.get("image_reference_files_attached") or 0))
    payload.setdefault("ai_usage", payload.get("ai_usage"))
    payload.setdefault("knowledge_base_id", payload.get("knowledge_base_id"))
    payload.setdefault("knowledge_base_name", payload.get("knowledge_base_name"))
    payload.setdefault("knowledge_chunks_used", payload.get("knowledge_chunks_used"))
    payload.setdefault("knowledge_chunks", payload.get("knowledge_chunks") or [])
    payload.setdefault("history_id", int(history_item.get("id") or 0) or None)
    return VKAIPostResponse.model_validate(payload)


def _build_recommendations_chat_prompt(
    *,
    report: dict,
    message: str,
    language: str,
    chat_history: list[dict],
) -> str:
    source = report.get("source") if isinstance(report.get("source"), dict) else {}
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    ai = report.get("ai") if isinstance(report.get("ai"), dict) else {}
    recommendations = report.get("recommendations") if isinstance(report.get("recommendations"), list) else []
    audience_profile = report.get("audience_profile") if isinstance(report.get("audience_profile"), dict) else {}

    compact = {
        "source": {
            "name": source.get("name"),
            "screen_name": source.get("screen_name"),
            "members_count": source.get("members_count"),
            "activity": source.get("activity"),
        },
        "metrics": {
            "average_views": metrics.get("average_views"),
            "average_likes": metrics.get("average_likes"),
            "average_comments": metrics.get("average_comments"),
            "posts_per_day": metrics.get("posts_per_day"),
            "total_posts_analyzed": metrics.get("total_posts_analyzed"),
        },
        "ai": {
            "summary": ai.get("summary"),
            "search_tags": (ai.get("search_tags") or [])[:12],
            "audience_interests": (ai.get("audience_interests") or [])[:8],
            "potential_competitors": (ai.get("potential_competitors") or [])[:8],
            "limitations": (ai.get("limitations") or [])[:6],
        },
        "audience_profile": {
            "content_preferences": (audience_profile.get("content_preferences") or [])[:4],
            "engagement_style": (audience_profile.get("engagement_style") or [])[:4],
            "summary": audience_profile.get("summary"),
        },
        "recommendations": recommendations[:6],
    }

    history_lines = []
    for item in chat_history[-12:]:
        role = "user" if str(item.get("role")) == "user" else "assistant"
        text = str(item.get("text") or "").strip()
        if text:
            history_lines.append(f"{role}: {text[:600]}")
    history_text = "\n".join(history_lines) if history_lines else "no previous chat history"

    return (
        "Ты senior SMM-стратег по VK.\n"
        "Отвечай только по данным отчета ниже, не придумывай фактов.\n"
        "Дай практичный план с конкретными шагами, примерами форматов и метриками контроля.\n"
        "Структура: 1) гипотеза, 2) что сделать в ближайшие 7 дней, 3) KPI/метрики.\n"
        "Пиши кратко, предметно и по делу.\n"
        "Формат ответа: обычный текст с переносами строк, без markdown.\n"
        "Каждый шаг плана — с новой строки, нумерация строго 1., 2., 3.\n\n"
        f"Language: {language or 'ru'}\n"
        f"Report JSON:\n{json.dumps(compact, ensure_ascii=False)}\n\n"
        f"Chat history:\n{history_text}\n\n"
        f"User question:\n{message}"
    )


def _fallback_recommendations_answer(report: dict, message: str) -> str:
    ai = report.get("ai") if isinstance(report.get("ai"), dict) else {}
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    search_tags = [str(tag).strip() for tag in (ai.get("search_tags") or []) if str(tag).strip()][:4]
    recommendations = report.get("recommendations") if isinstance(report.get("recommendations"), list) else []

    niche = ", ".join(search_tags) if search_tags else "ключевые темы сообщества"
    baseline_views = int(metrics.get("average_views") or 0)
    baseline_likes = int(metrics.get("average_likes") or 0)
    baseline_comments = int(metrics.get("average_comments") or 0)

    lines = [
        f"Фокус по вашему вопросу: {message}.",
        f"Гипотеза: рост даст контент вокруг тем {niche} с повторяющимися форматами и явным CTA.",
        "План на 7 дней: 1 образовательный пост, 1 кейс/разбор, 1 вовлекающий пост с вопросом, 1 сравнение с конкурентами.",
        (
            f"KPI на следующую неделю: средние просмотры > {max(1, int(baseline_views * 1.15))}, "
            f"лайки > {max(1, int(baseline_likes * 1.15))}, комментарии > {max(1, int(baseline_comments * 1.2))}."
        ),
    ]
    for rec in recommendations[:2]:
        if not isinstance(rec, dict):
            continue
        title = str(rec.get("title") or "").strip()
        action = str(rec.get("action") or "").strip()
        if title and action:
            lines.append(f"{title}: {action}")
    return "\n".join(lines)


def _format_chat_answer_text(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not value:
        return ""
    value = re.sub(r"\n{3,}", "\n\n", value)
    if "\n" not in value and len(value) >= 180:
        # LLM sometimes returns one long paragraph; split by sentences/numbering.
        value = re.sub(r"\s+(?=\d+\.)", "\n", value)
        value = re.sub(r"(?<=[.!?])\s+(?=[А-ЯA-Z0-9])", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
    lines = [" ".join(line.split()).strip() for line in value.split("\n")]
    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        if line:
            cleaned.append(line)
            prev_blank = False
        elif not prev_blank:
            cleaned.append("")
            prev_blank = True
    return "\n".join(cleaned).strip()


@router.get("/browser/status", summary="VK browser profile status")
def vk_browser_status():
    profile_dir = vk_browser_profile_dir()
    return {
        "profile_dir": str(profile_dir),
        "profile_exists": has_vk_browser_profile(),
    }


@router.post("/browser/login", summary="Open browser for VK login")
def vk_browser_login():
    return launch_vk_browser_login()


@router.post(
    "/posts/publish",
    response_model=VKPublishResponse,
    summary="Publish a VK post",
    description="Publishes a post via wall.post.",
)
def vk_publish_post(
    payload: VKPublishRequest,
    publisher: VKPublisher = Depends(get_vk_publisher),
):
    try:
        access_token = _resolve_access_token()
        if not access_token:
            raise VKAuthorizationError("VK access_token is required")
        group_id = _default_group_id()
        if not group_id:
            raise VKAuthorizationError("VK_GROUP_ID is required")
        result = publisher.publish(
            access_token=access_token,
            payload=VKPublishPayload(
                group_id=group_id,
                message=payload.message,
                attachments=None,
                publish_date=None,
            ),
        )
    except VKAuthorizationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except VKOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VKPublishResponse(
        post_id=result.post_id,
        owner_id=result.owner_id,
    )


@router.post(
    "/posts/generate",
    response_model=VKAIPostResponse,
    summary="Generate VK post with selected AI provider (optional publish)",
)
def vk_generate_post(
    payload: VKAIPostRequest,
    publisher: VKPublisher = Depends(get_vk_publisher),
    vk_client: VKClient = Depends(get_vk_client),
):
    try:
        client, ai_provider, _, _ = _build_text_ai_client(payload.ai_provider)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"AI is not configured: {exc}") from exc

    # For publishing, prioritize community token, but keep user-token fallback
    # for media upload methods that are often unavailable for group auth.
    group_token = _load_group_token()
    resolved_tokens = _resolve_access_tokens()
    if group_token:
        access_tokens = [group_token] + [token for token in resolved_tokens if token != group_token]
    else:
        access_tokens = resolved_tokens
    access_token = access_tokens[0] if access_tokens else None
    if payload.publish and not access_tokens:
        raise HTTPException(status_code=401, detail="VK access_token is required to publish")
    group_id = _default_group_id()
    if payload.publish and not group_id:
        raise HTTPException(status_code=400, detail="group_id is required to publish")

    context: dict[str, object] = {}
    if group_id and access_token:
        try:
            group_info = vk_client.call_api(
                "groups.getById",
                access_token,
                group_id=str(group_id),
                fields="members_count,screen_name,name,description,activity",
            )
            if group_info:
                context["group"] = group_info[0]
        except Exception:
            pass

    selected_kb = _knowledge_store.get_active()

    kb_excerpt = None
    kb_id = None
    kb_name = None
    kb_snippets: list[dict] = []
    kb_chunks_payload: list[VKRAGChunkUsedResponse] = []
    if selected_kb:
        # Build query from prompt + theme + tone, but keep prompt as the main signal.
        # Theme/tone are passed as contextual hints, while retrieval filters
        # in VKKnowledgeStore suppress weak accidental matches.
        kb_query_parts: list[str] = []
        prompt_text = (payload.prompt or "").strip()
        if prompt_text:
            kb_query_parts.append(prompt_text)
        theme_text = str(payload.theme or "").strip()
        if theme_text:
            kb_query_parts.append(f"тема: {theme_text}")
        tone_text = str(payload.tone or "").strip()
        if tone_text:
            kb_query_parts.append(f"тон: {tone_text}")
        content_type_text = str(payload.content_type or "").strip().lower()
        if content_type_text and content_type_text != "text":
            kb_query_parts.append(f"тип контента: {content_type_text}")

        kb_query = " | ".join(kb_query_parts).strip()
        if not kb_query:
            kb_query = prompt_text or theme_text or tone_text or content_type_text
        kb_snippets = _knowledge_store.retrieve_relevant(
            query=kb_query,
            knowledge_base_id=str(selected_kb.get("id") or ""),
            max_chars=5000,
        )
        kb_chunks_payload = _build_kb_chunks_payload(kb_snippets)
        kb_excerpt = _knowledge_store.build_retrieved_context(kb_snippets, max_chars=5000)
        kb_id = str(selected_kb.get("id") or "")
        kb_name = str(selected_kb.get("name") or "")
        context["knowledge_base"] = {
            "id": kb_id,
            "name": kb_name,
            "language": str(selected_kb.get("language") or "ru"),
            "content_excerpt": kb_excerpt or "",
            "snippets": [
                {
                    "title": str(item.get("title") or ""),
                    "score": float(item.get("score") or 0.0),
                }
                for item in kb_snippets
            ],
        }

    logger.info(
        "VK_POST_GENERATE_PARSED prompt_chars=%s content_type=%s kb_chunks=%s kb_excerpt_chars=%s context_chars=%s",
        len((payload.prompt or "").strip()),
        payload.content_type,
        len(kb_snippets),
        len(kb_excerpt or ""),
        len(json.dumps(context, ensure_ascii=False)),
    )
    logger.info(
        "VK_POST_GENERATE_AI_REQUEST:\n%s",
        _json_for_log(
            {
                "prompt": payload.prompt,
                "language": payload.language,
                "length": payload.length,
                "theme": payload.theme,
                "tone": payload.tone,
                "content_type": payload.content_type,
                "knowledge_base_excerpt": kb_excerpt or "",
                "knowledge_chunks_used": kb_chunks_payload,
                "context": context,
            }
        ),
    )

    try:
        generated = client.generate_post(
            prompt=payload.prompt,
            context=context,
            language=payload.language,
            length=payload.length,
            theme=payload.theme,
            tone=payload.tone,
            knowledge_base=kb_excerpt,
            content_type=payload.content_type,
        )
    except Exception as exc:
        logger.exception("VK_POST_GENERATE_AI_ERROR: %s", exc)
        raise HTTPException(status_code=502, detail=f"{client.provider_name()} error: {exc}") from exc

    logger.info(
        "VK_POST_GENERATE_AI_RESPONSE:\n%s",
        _json_for_log(
            {
                "content_type": generated.content_type,
                "text": generated.text,
                "story_frames": generated.story_frames,
                "image_prompt": generated.image_prompt,
                "video_script": generated.video_script,
            }
        ),
    )

    text = generated.text
    generated_image_base64: str | None = None
    generated_image_mime_type: str | None = None
    image_bytes: bytes | None = None
    image_mime_type: str | None = None
    media_usage_client = None

    resolved_image_prompt: str | None = generated.image_prompt

    if generated.content_type == "image":
        try:
            media_client = _build_media_ai_client(ai_provider)
            if media_client is None:
                raise HTTPException(
                    status_code=400,
                    detail="Image generation requires media-capable provider (configure GigaChat or switch provider).",
                )
            media_usage_client = media_client
            fallback_image_prompt = _build_image_prompt_from_generated_text(
                generated_text=text,
                fallback_prompt=payload.prompt,
                theme=payload.theme,
                tone=payload.tone,
                ai_image_prompt=generated.image_prompt,
            )
            image_prompt = client.build_image_prompt_from_post(
                post_text=text,
                language=payload.language,
                theme=payload.theme,
                tone=payload.tone,
                fallback_prompt=fallback_image_prompt,
            )
            resolved_image_prompt = image_prompt
            image_bytes, image_mime_type, _ = media_client.generate_image(
                prompt=image_prompt,
                language=payload.language,
                theme=payload.theme,
                tone=payload.tone,
                knowledge_base=kb_excerpt,
            )
            generated_image_base64 = base64.b64encode(image_bytes).decode("ascii")
            generated_image_mime_type = image_mime_type
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Image generation failed: {exc}") from exc

    if payload.publish:
        result = None
        last_error: Exception | None = None
        media_error: Exception | None = None
        media_attached: bool | None = None
        publish_note: str | None = None
        try:
            if generated.content_type == "video":
                video_prompt = (generated.video_script or "").strip() or text or payload.prompt
                media_client = _build_media_ai_client(ai_provider)
                if media_client is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Video generation requires media-capable provider (configure GigaChat or switch provider).",
                    )
                media_usage_client = media_client
                video_bytes, video_mime_type, _ = media_client.generate_video(
                    prompt=video_prompt,
                    language=payload.language,
                    theme=payload.theme,
                    tone=payload.tone,
                    knowledge_base=kb_excerpt,
                )

            for token in access_tokens:
                try:
                    if generated.content_type == "image":
                        if image_bytes is None or image_mime_type is None:
                            raise HTTPException(status_code=502, detail="Generated image is missing")
                        result = publisher.publish_with_generated_image(
                            access_token=token,
                            group_id=group_id or 0,
                            message=text,
                            image_bytes=image_bytes,
                            image_mime_type=image_mime_type,
                        )
                        media_attached = True
                    elif generated.content_type == "video":
                        result = publisher.publish_with_generated_video(
                            access_token=token,
                            group_id=group_id or 0,
                            message=text,
                            video_bytes=video_bytes,
                            video_mime_type=video_mime_type,
                            video_title=(payload.theme or "Generated video").strip()[:80] or "Generated video",
                        )
                        media_attached = True
                    else:
                        result = publisher.publish(
                            access_token=token,
                            payload=VKPublishPayload(
                                group_id=group_id or 0,
                                message=text,
                                attachments=None,
                                publish_date=None,
                            ),
                        )
                    break
                except VKAuthorizationError as exc:
                    last_error = exc
                    continue
                except VKOperationError as exc:
                    last_error = exc
                    if _is_group_auth_restriction(exc):
                        continue
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
            if result is None and last_error is not None:
                if (
                    generated.content_type in {"image", "video"}
                    and isinstance(last_error, VKOperationError)
                    and _is_group_auth_restriction(last_error)
                    and access_tokens
                ):
                    # Group tokens often cannot call media upload methods.
                    # Fallback: publish text-only post with generated media concept.
                    fallback_message = text
                    if generated.content_type == "image" and generated.image_prompt:
                        fallback_message = f"{text}\n\nВизуал: {generated.image_prompt}"
                    if generated.content_type == "video" and generated.video_script:
                        fallback_message = f"{text}\n\nСценарий видео: {generated.video_script}"
                    result = publisher.publish(
                        access_token=access_tokens[0],
                        payload=VKPublishPayload(
                            group_id=group_id or 0,
                            message=fallback_message.strip(),
                            attachments=None,
                            publish_date=None,
                        ),
                    )
                    media_attached = False
                    publish_note = "VK media upload is unavailable for current token; published text-only fallback."

            if result is None and last_error is not None:
                if isinstance(last_error, VKAuthorizationError):
                    raise HTTPException(status_code=401, detail=str(last_error)) from last_error
                if isinstance(last_error, VKOperationError):
                    raise HTTPException(
                        status_code=400,
                        detail=f"{last_error}. Try user token for media publishing.",
                    ) from last_error
        except VKAuthorizationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except VKOperationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            media_error = exc
        if result is None:
            if media_error is not None:
                raise HTTPException(status_code=502, detail=f"Image/video generation or upload failed: {media_error}") from media_error
            raise HTTPException(status_code=502, detail="Failed to publish generated content with available tokens")

        char_count = len(text)
        word_count = len([w for w in text.split() if w.strip()])
        token_estimate = max(1, int(round(char_count / 4)))
        ai_usage = _build_ai_usage_payload(client, media_usage_client)
        logger.info(
            "VK_POST_GENERATE_USAGE provider=%s requests=%s media_requests=%s usage=%s usage_events=%s",
            getattr(client, "provider_name", lambda: "unknown")(),
            getattr(client, "get_request_count", lambda: None)(),
            getattr(media_usage_client, "get_request_count", lambda: None)() if media_usage_client else None,
            ai_usage.model_dump() if ai_usage else None,
            getattr(client, "get_usage_events", lambda: [])(),
        )
        response_payload = VKAIPostResponse(
            text=text,
            published=True,
            post_id=result.post_id,
            owner_id=result.owner_id,
            media_attached=media_attached,
            publish_note=publish_note,
            char_count=char_count,
            word_count=word_count,
            token_estimate=token_estimate,
            token_estimate_method="chars/4",
            content_type=generated.content_type,
            theme=payload.theme,
            tone=payload.tone,
            story_frames=generated.story_frames,
            image_prompt=resolved_image_prompt,
            video_script=generated.video_script,
            generated_image_base64=generated_image_base64,
            generated_image_mime_type=generated_image_mime_type,
            knowledge_base_id=kb_id,
            knowledge_base_name=kb_name,
            knowledge_chunks_used=len(kb_snippets) if kb_snippets else None,
            knowledge_chunks=kb_chunks_payload,
            ai_usage=ai_usage,
        )
        history_id = _safe_save_generated_history(
            request_payload=payload.model_dump(mode="json"),
            response_payload=response_payload.model_dump(mode="json"),
        )
        if history_id:
            response_payload = response_payload.model_copy(update={"history_id": int(history_id)})
        return response_payload

    char_count = len(text)
    word_count = len([w for w in text.split() if w.strip()])
    token_estimate = max(1, int(round(char_count / 4)))
    ai_usage = _build_ai_usage_payload(client, media_usage_client)
    logger.info(
        "VK_POST_GENERATE_USAGE provider=%s requests=%s media_requests=%s usage=%s usage_events=%s",
        getattr(client, "provider_name", lambda: "unknown")(),
        getattr(client, "get_request_count", lambda: None)(),
        getattr(media_usage_client, "get_request_count", lambda: None)() if media_usage_client else None,
        ai_usage.model_dump() if ai_usage else None,
        getattr(client, "get_usage_events", lambda: [])(),
    )
    response_payload = VKAIPostResponse(
        text=text,
        published=False,
        post_id=None,
        owner_id=None,
        media_attached=None,
        publish_note=None,
        char_count=char_count,
        word_count=word_count,
        token_estimate=token_estimate,
        token_estimate_method="chars/4",
        content_type=generated.content_type,
        theme=payload.theme,
        tone=payload.tone,
        story_frames=generated.story_frames,
        image_prompt=resolved_image_prompt,
        video_script=generated.video_script,
        generated_image_base64=generated_image_base64,
        generated_image_mime_type=generated_image_mime_type,
        knowledge_base_id=kb_id,
        knowledge_base_name=kb_name,
        knowledge_chunks_used=len(kb_snippets) if kb_snippets else None,
        knowledge_chunks=kb_chunks_payload,
        ai_usage=ai_usage,
    )
    history_id = _safe_save_generated_history(
        request_payload=payload.model_dump(mode="json"),
        response_payload=response_payload.model_dump(mode="json"),
    )
    if history_id:
        response_payload = response_payload.model_copy(update={"history_id": int(history_id)})
    return response_payload


@router.post(
    "/posts/regenerate-image",
    response_model=VKRegenerateImageResponse,
    summary="Regenerate image for existing generated/edited post text",
)
def vk_regenerate_image(payload: VKRegenerateImageRequest):
    try:
        client, ai_provider, _, _ = _build_text_ai_client(payload.ai_provider)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"AI is not configured: {exc}") from exc
    post_text = (payload.post_text or "").strip()
    if not post_text:
        raise HTTPException(status_code=400, detail="post_text is required")

    manual_prompt = (payload.image_prompt or "").strip()
    media_client = None
    try:
        resolved_prompt = (
            manual_prompt
            or client.build_image_prompt_from_post(
                post_text=post_text,
                language=payload.language,
                theme=payload.theme,
                tone=payload.tone,
                fallback_prompt=post_text[:240],
            )
        ).strip()
        if not resolved_prompt:
            raise HTTPException(status_code=400, detail="Could not build image prompt from post text")

        media_client = _build_media_ai_client(ai_provider)
        if media_client is None:
            raise HTTPException(
                status_code=400,
                detail="Image generation requires media-capable provider (configure GigaChat or switch provider).",
            )
        image_bytes, image_mime_type, _ = media_client.generate_image(
            prompt=resolved_prompt,
            language=payload.language,
            theme=payload.theme,
            tone=payload.tone,
            knowledge_base=None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image regeneration failed: {exc}") from exc

    return VKRegenerateImageResponse(
        image_prompt=resolved_prompt,
        generated_image_base64=base64.b64encode(image_bytes).decode("ascii"),
        generated_image_mime_type=image_mime_type,
        ai_usage=_build_ai_usage_payload(client, media_client),
    )


@router.post(
    "/group/analyze",
    response_model=VKGroupAnalyzeResponse,
    summary="Analyze VK group with selected AI provider",
)
def vk_group_analyze(
    payload: VKGroupAnalyzeRequest,
    vk_client: VKClient = Depends(get_vk_client),
):
    logger.warning(
        "VK_ANALYZE_TRACE_START source=%s post_limit=%s language=%s",
        payload.source,
        payload.post_limit,
        payload.language,
    )
    normalized, resolved_group_id = _resolve_group_identity(payload.source)
    group = {
        "id": int(resolved_group_id or 0),
        "name": normalized,
        "screen_name": normalized,
        "members_count": None,
        "description": None,
        "activity": None,
        "site": None,
    }
    group_id = int(resolved_group_id or 0)

    posts = []
    metrics_views: list[int] = []
    metrics_likes: list[int] = []
    metrics_comments: list[int] = []
    metrics_reposts: list[int] = []
    post_dates: list[int] = []
    top_posts = []
    limitations = []

    try:
        public_group = fetch_public_group_data(normalized, group_id=group_id or None, limit=payload.post_limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"VK public parser failed: {exc}") from exc

    if public_group.name and not _is_bad_public_group_name(public_group.name):
        group["name"] = public_group.name
    group["screen_name"] = public_group.screen_name or group.get("screen_name") or normalized
    (
        posts,
        metrics_views,
        metrics_likes,
        metrics_comments,
        metrics_reposts,
        post_dates,
        top_posts,
    ) = _build_payload_from_public_group(public_group)
    limitations.append("Used public page parser because VK API wall access is not used.")

    if not group_id:
        for post in public_group.posts or []:
            inferred_group_id = _public_post_owner_to_group_id(post.post_id)
            if inferred_group_id:
                group_id = inferred_group_id
                group["id"] = inferred_group_id
                break

    logger.warning(
        "VK_ANALYZE_PARSED group=%s screen_name=%s posts=%s top_posts=%s",
        group.get("name"),
        group.get("screen_name"),
        len(posts),
        len(top_posts),
    )
    logger.warning(
        "VK_ANALYZE_PARSED_PAYLOAD:\n%s",
        _json_for_log(
            {
                "group": group,
                "parsed_posts": posts,
                "parsed_top_posts": top_posts,
            }
        ),
    )

    top_posts = [
        item
        for item in top_posts
        if any(int(item.get(metric) or 0) > 0 for metric in ("views", "likes", "comments", "reposts"))
    ]
    top_posts = sorted(
        top_posts,
        key=lambda p: (
            p.get("views", 0),
            p.get("likes", 0) + p.get("comments", 0) * 2 + p.get("reposts", 0) * 3,
        ),
        reverse=True,
    )[:5]
    if not posts:
        limitations.append("No posts available for analysis or access is limited.")

    metrics = VKGroupMetricsResponse(
        average_views=_avg(metrics_views),
        average_likes=_avg(metrics_likes),
        average_comments=_avg(metrics_comments),
        average_reposts=_avg(metrics_reposts),
        posts_per_day=_posts_per_day(post_dates),
        total_posts_analyzed=len(posts),
        top_posts=top_posts,
        limitations=limitations,
    )

    local_ai_payload, local_ai_status = build_local_vk_insights_with_context(
        group_name=group.get("name", ""),
        screen_name=group.get("screen_name") or normalized,
        posts=posts[: max(1, min(len(posts), 50))],
        metrics=metrics.model_dump(),
        group_description=group.get("description"),
        group_activity=group.get("activity"),
    )
    ai_insights = VKGroupAIInsights(**local_ai_payload)
    ai_status = local_ai_status
    recommendations: list[dict] = []
    ai_identity_tags: list[str] = []
    ai_usage_payload: VKAIUsageResponse | None = None

    try:
        client, provider, provider_model, provider_auth_mode = _build_text_ai_client(payload.ai_provider)
        ai_payload = {
            "group": {
                "id": group.get("id"),
                "name": group.get("name"),
                "screen_name": group.get("screen_name"),
                "members_count": group.get("members_count"),
                "description": group.get("description"),
                "activity": group.get("activity"),
                "site": group.get("site"),
            },
            "metrics": metrics.model_dump(),
            "posts": posts[: max(1, min(len(posts), 30))],
            "local_clusters": local_ai_payload,
        }
        logger.warning("VK_ANALYZE_AI_REQUEST:\n%s", _json_for_log(ai_payload))
        ai_result = _call_with_retries(
            lambda: client.analyze_group(payload=ai_payload, language=payload.language),
            attempts=3,
            base_delay_sec=0.9,
        )
        logger.warning(
            "VK_ANALYZE_AI_RESPONSE:\n%s",
            _json_for_log(
                {
                    "audience_interests": ai_result.audience_interests,
                    "audience_age": ai_result.audience_age,
                    "audience_activity": ai_result.audience_activity,
                    "potential_competitors": ai_result.potential_competitors,
                    "search_tags": ai_result.search_tags,
                    "summary": ai_result.summary,
                    "limitations": ai_result.limitations,
                    "recommendations": [
                        {
                            "title": rec.title,
                            "action": rec.action,
                            "rationale": rec.rationale,
                        }
                        for rec in (ai_result.recommendations or [])
                    ],
                }
            ),
        )
        ai_insights = VKGroupAIInsights(
            audience_interests=ai_result.audience_interests,
            audience_age=ai_result.audience_age,
            audience_activity=ai_result.audience_activity,
            potential_competitors=ai_result.potential_competitors,
            search_tags=ai_result.search_tags,
            summary=ai_result.summary,
            limitations=ai_result.limitations,
        )
        recommendations = [
            {
                "title": rec.title,
                "action": rec.action,
                "rationale": rec.rationale,
            }
            for rec in (ai_result.recommendations or [])
            if rec.title and rec.action and rec.rationale
        ][:5]
        try:
            ai_identity_tags = _call_with_retries(
                lambda: client.generate_search_tags_from_group(
                    group={
                        "name": group.get("name"),
                        "screen_name": group.get("screen_name"),
                        "activity": group.get("activity"),
                        "description": group.get("description"),
                        "site": group.get("site"),
                    },
                    language=payload.language,
                    limit=10,
                ),
                attempts=2,
                base_delay_sec=0.7,
            )
        except Exception:
            ai_identity_tags = []
        ai_status = {
            "enabled": True,
            "available": True,
            "enhanced": True,
            "provider": provider,
            "model": provider_model,
            "auth_mode": provider_auth_mode,
            "message": f"{provider} analysis completed",
        }
        ai_usage_payload = _build_ai_usage_payload(client)
        logger.warning(
            "VK_ANALYZE_USAGE provider=%s requests=%s usage=%s usage_events=%s",
            getattr(client, "provider_name", lambda: "unknown")(),
            getattr(client, "get_request_count", lambda: None)(),
            ai_usage_payload.model_dump() if ai_usage_payload else None,
            getattr(client, "get_usage_events", lambda: [])(),
        )
    except Exception as exc:
        logger.exception("VK_ANALYZE_AI_ERROR: %s", exc)
        provider = _resolve_ai_provider(payload.ai_provider)
        error_text = " ".join(str(exc).split()).strip()
        if len(error_text) > 220:
            error_text = error_text[:220].rstrip() + "..."
        ai_status = {
            "enabled": provider != "none",
            "available": False,
            "enhanced": False,
            "provider": provider if provider != "none" else "local",
            "model": None,
            "auth_mode": None,
            "message": (
                f"AI temporarily unavailable, used local fallback analysis: {error_text}"
                if error_text
                else "AI temporarily unavailable, used local fallback analysis."
            ),
        }

    group_context_name = f"{group.get('name', '')} {group.get('screen_name') or ''}".strip()

    sparse_posts = _is_sparse_post_content(posts)
    logger.warning(
        "VK_ANALYZE_TAG_MODE sparse_posts=%s posts=%s ai_identity_tags=%s ai_search_tags=%s",
        sparse_posts,
        len(posts),
        len(ai_identity_tags or []),
        len(ai_insights.search_tags or []),
    )

    raw_tags: list[str] = []
    # When posts are sparse/noisy, prioritize identity tags generated from group card.
    if sparse_posts and ai_identity_tags:
        raw_tags.extend(ai_identity_tags)
        raw_tags.extend(ai_insights.potential_competitors or [])
        raw_tags.extend(ai_insights.search_tags or [])
    else:
        raw_tags.extend(ai_identity_tags or [])
        raw_tags.extend(ai_insights.search_tags or [])
        raw_tags.extend(ai_insights.potential_competitors or [])

    if not raw_tags:
        raw_tags.extend(_extract_ai_search_tags(ai_insights, limit=10))
    if not raw_tags:
        raw_tags.extend(local_ai_payload.get("search_tags") or [])

    ai_tags = _finalize_search_tags_for_vk_ru(
        raw_tags,
        group_name=group_context_name,
        group_description=group.get("description"),
        group_activity=group.get("activity"),
        source_posts=posts,
        limit=8,
    )
    if ai_tags:
        ai_tags = _filter_tags_by_group_context(
            ai_tags,
            group_name=group_context_name,
            group_description=group.get("description"),
            group_activity=group.get("activity"),
            limit=8,
        )
    ai_insights.search_tags = ai_tags
    ai_insights.audience_interests = _normalize_ai_russian_list(
        ai_insights.audience_interests,
        fallback=ai_tags,
    )
    if _summary_looks_bad(ai_insights.summary):
        ai_insights.summary = _build_group_level_summary(
            group_name=group.get("name", "") or (group.get("screen_name") or normalized),
            screen_name=group.get("screen_name"),
            group_activity=group.get("activity"),
            group_description=group.get("description"),
            tags=ai_tags,
            posts_analyzed=len(posts),
        )
    ai_topic_labels = _extract_ai_topic_labels(ai_insights, limit=4)

    competitors_found: list[dict] = []
    logger.warning(
        "VK_ANALYZE_COMPETITOR_INPUT ai_tags=%s potential_competitors=%s",
        ai_tags,
        ai_insights.potential_competitors or [],
    )
    if ai_tags:
        try:
            competitors_found = _search_vk_competitors(
                vk_client,
                "",
                current_group_id=group_id,
                current_screen_name=group.get("screen_name"),
                current_name=group.get("name", ""),
                current_activity=group.get("activity"),
                current_description=group.get("description"),
                topic_clusters=[],
                source_posts=posts,
                ai_tags=ai_tags,
                topic_labels=ai_topic_labels,
                use_ai_tags_only=True,
                public_only=True,
                limit=5,
            )
        except Exception as exc:
            logger.exception("VK_ANALYZE_COMPETITOR_SEARCH_ERROR: %s", exc)
            competitors_found = []

    audience_profile = _build_audience_profile(ai_insights, metrics)

    response_payload = VKGroupAnalyzeResponse(
        source=VKAnalyticsSourceResponse(
            platform="vk",
            group_id=int(group.get("id", 0) or 0),
            name=group.get("name", ""),
            screen_name=group.get("screen_name"),
            url=f"https://vk.com/{group.get('screen_name') or normalized}",
            members_count=group.get("members_count"),
            activity=group.get("activity"),
            description=group.get("description"),
            site=group.get("site"),
        ),
        group={
            "group_id": int(group.get("id", 0) or 0),
            "name": group.get("name", ""),
            "screen_name": group.get("screen_name"),
            "members_count": group.get("members_count"),
        },
        metrics=metrics,
        ai=ai_insights,
        audience_profile=VKAudienceProfileResponse(**audience_profile),
        competitors_found=[VKCompetitorFoundResponse(**item) for item in competitors_found],
        recommendations=[VKAnalyticsRecommendationResponse(**item) for item in recommendations],
        ai_status=ai_status,
        ai_usage=ai_usage_payload,
    )
    history_id = _safe_save_analysis_history(
        source_input=payload.source,
        post_limit=payload.post_limit,
        language=payload.language,
        report=response_payload.model_dump(mode="json"),
    )
    if history_id:
        response_payload = response_payload.model_copy(update={"history_id": int(history_id)})
    logger.warning(
        "VK_ANALYZE_TRACE_END source=%s posts=%s tags=%s competitors=%s history_id=%s",
        payload.source,
        int(metrics.total_posts_analyzed or 0),
        len(ai_insights.search_tags or []),
        len(competitors_found or []),
        history_id,
    )
    return response_payload


@router.post(
    "/group/report",
    summary="Render VK analytics report as PNG",
    response_class=StreamingResponse,
)
def vk_group_report(
    payload: VKGroupAnalyzeRequest,
    vk_client: VKClient = Depends(get_vk_client),
):
    report = vk_group_analyze(payload, vk_client)
    image_bytes = _render_group_report_png(report)
    return StreamingResponse(BytesIO(image_bytes), media_type="image/png")


@router.get(
    "/posts/generate/history",
    response_model=VKPostGenerateHistoryListResponse,
    summary="List post generation history",
)
def vk_posts_generate_history(limit: int = Query(default=30, ge=1, le=200)):
    return VKPostGenerateHistoryListResponse(items=list_generated_posts(limit=limit))


@router.get(
    "/posts/generate/history/{history_id}",
    response_model=VKPostGenerateHistoryItemResponse,
    summary="Get one post generation history item",
)
def vk_posts_generate_history_item(history_id: int):
    item = get_generated_post(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="Generation history item not found")
    report = _coerce_post_report(item)
    payload = dict(item)
    payload["report"] = report
    return VKPostGenerateHistoryItemResponse.model_validate(payload)


@router.delete(
    "/posts/generate/history",
    response_model=VKPostGenerateHistoryClearResponse,
    summary="Clear post generation history",
)
def vk_posts_generate_history_clear():
    cleared = clear_generated_posts_history()
    return VKPostGenerateHistoryClearResponse(cleared=cleared)


@router.delete(
    "/posts/generate/history/{history_id}",
    response_model=VKPostGenerateHistoryDeleteItemResponse,
    summary="Delete one post generation history item",
)
def vk_posts_generate_history_delete_item(history_id: int):
    deleted = delete_generated_post(history_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Generation history item not found")
    return VKPostGenerateHistoryDeleteItemResponse(deleted=True, history_id=history_id)


@router.get(
    "/group/analyze/history",
    response_model=VKGroupAnalyzeHistoryListResponse,
    summary="List VK group analysis history",
)
def vk_group_analyze_history(limit: int = Query(default=30, ge=1, le=200)):
    return VKGroupAnalyzeHistoryListResponse(items=list_analysis_history(limit=limit))


@router.get(
    "/group/analyze/history/{history_id}",
    response_model=VKGroupAnalyzeHistoryItemResponse,
    summary="Get one VK group analysis history item",
)
def vk_group_analyze_history_item(history_id: int):
    item = get_analysis_history_item(history_id)
    if not item:
        raise HTTPException(status_code=404, detail="Analysis history item not found")

    report_payload = item.get("report") if isinstance(item.get("report"), dict) else {}
    try:
        report = VKGroupAnalyzeResponse.model_validate(report_payload)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Stored analysis report has unsupported format: {exc}",
        ) from exc

    payload = dict(item)
    payload["report"] = report
    payload["chat_messages"] = _normalize_chat_messages(
        payload.get("chat_messages") if isinstance(payload.get("chat_messages"), list) else [],
        limit=120,
    )
    return VKGroupAnalyzeHistoryItemResponse.model_validate(payload)


@router.delete(
    "/group/analyze/history",
    response_model=VKGroupAnalyzeHistoryClearResponse,
    summary="Clear VK group analysis history",
)
def vk_group_analyze_history_clear():
    cleared = clear_analysis_history()
    return VKGroupAnalyzeHistoryClearResponse(cleared=cleared)


@router.delete(
    "/group/analyze/history/{history_id}",
    response_model=VKGroupAnalyzeHistoryDeleteItemResponse,
    summary="Delete one VK group analysis history item",
)
def vk_group_analyze_history_delete_item(history_id: int):
    deleted = delete_analysis_history_item(history_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis history item not found")
    return VKGroupAnalyzeHistoryDeleteItemResponse(deleted=True, history_id=history_id)


@router.post(
    "/group/recommendations/chat",
    response_model=VKRecommendationsChatResponse,
    summary="Follow-up recommendations chat based on analysis report",
)
def vk_group_recommendations_chat(payload: VKRecommendationsChatRequest):
    message = " ".join(str(payload.message or "").split()).strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    history_item: dict | None = None
    if payload.history_id:
        history_item = get_analysis_history_item(int(payload.history_id))

    report_payload = payload.report if isinstance(payload.report, dict) else {}
    if not report_payload and history_item and isinstance(history_item.get("report"), dict):
        report_payload = history_item.get("report") or {}
    if not report_payload:
        raise HTTPException(status_code=400, detail="report is required")

    chat_history = _normalize_chat_messages(
        history_item.get("chat_messages") if history_item else [],
        limit=120,
    )

    answer = ""
    try:
        client, _, _, _ = _build_text_ai_client(None)
        chat_fn = getattr(client, "_chat", None)
        if callable(chat_fn):
            prompt = _build_recommendations_chat_prompt(
                report=report_payload,
                message=message,
                language=payload.language,
                chat_history=chat_history,
            )
            answer = str(chat_fn(prompt) or "").strip()
            answer = re.sub(r"^```(?:json|text|markdown)?\s*", "", answer, flags=re.IGNORECASE)
            answer = re.sub(r"\s*```$", "", answer, flags=re.IGNORECASE)
            answer = re.sub(r"\n{3,}", "\n\n", answer).strip()
    except Exception:
        answer = ""

    if not answer:
        answer = _fallback_recommendations_answer(report_payload, message)
    answer = _format_chat_answer_text(answer)

    new_messages = _normalize_chat_messages(
        [
            {"role": "user", "text": message, "created_at": _utc_now_iso()},
            {"role": "assistant", "text": answer, "created_at": _utc_now_iso()},
        ],
        limit=2,
    )
    chat_messages = (chat_history + new_messages)[-120:]

    if payload.history_id:
        persisted = append_analysis_chat_messages(int(payload.history_id), new_messages)
        if persisted:
            chat_messages = _normalize_chat_messages(persisted, limit=120)

    return VKRecommendationsChatResponse(
        answer=answer,
        chat_messages=[VKRecommendationsChatMessage(**item) for item in chat_messages],
    )






