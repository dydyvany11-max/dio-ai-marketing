import json
import os
from collections import Counter
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:
    plt = None

from src.api.config import PROJECT_ROOT, is_gigachat_configured, load_gigachat_settings
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
    VKGroupAnalyzeResponse,
    VKGroupMetricsResponse,
    VKKnowledgeBaseItemResponse,
    VKKnowledgeBaseListResponse,
    VKKnowledgeBaseUploadRequest,
    VKKnowledgeBaseUploadResponse,
    VKTopicClusterResponse,
    VKPublishRequest,
    VKPublishResponse,
)
from src.api.services.errors import VKAuthorizationError, VKOperationError
from src.api.services.trends_engine import get_stopwords
from src.api.services.vk_ai import GigaChatVKClient
from src.api.services.vk_client import VKClient
from src.api.services.vk_knowledge import VKKnowledgeStore
from src.api.services.vk_local_analysis import build_local_vk_insights
from src.api.services.vk_public import (
    fetch_public_group_data,
    has_vk_browser_profile,
    launch_vk_browser_login,
    search_public_groups,
    vk_browser_profile_dir,
)
from src.api.services.vk_publisher import VKPublisher, VKPublishRequest as VKPublishPayload

router = APIRouter(prefix="/vk", tags=["VK"])
STOPWORDS = {word.lower() for word in get_stopwords()}
_MONTH_QUERY_STEMS = {
    "\u044f\u043d\u0432",
    "\u0444\u0435\u0432",
    "\u043c\u0430\u0440\u0442",
    "\u0430\u043f\u0440",
    "\u043c\u0430\u0439",
    "\u0438\u044e\u043d",
    "\u0438\u044e\u043b",
    "\u0430\u0432\u0433",
    "\u0441\u0435\u043d",
    "\u043e\u043a\u0442",
    "\u043d\u043e\u044f",
    "\u0434\u0435\u043a",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}
_WEAK_QUERY_WORDS = {
    "vk",
    "club",
    "public",
    "group",
    "community",
    "post",
    "posts",
    "news",
    "latest",
    "today",
    "yesterday",
    "video",
    "internet",
    "media",
    "internetmedia",
    "\u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442",
    "\u043c\u0435\u0434\u0438\u0430",
    "\u0438\u0437\u0434\u0430\u043d\u0438\u0435",
    "\u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442\u0438\u0437\u0434\u0430\u043d\u0438\u0435",
    "\u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442-\u0438\u0437\u0434\u0430\u043d\u0438\u0435",
    "\u0434\u043d\u044f",
    "\u043d\u043e\u0432\u043e\u0441\u0442\u0438",
    "\u043a\u043e\u0442\u043e\u0440\u044b\u0439",
    "\u043a\u043e\u0442\u043e\u0440\u0430\u044f",
    "\u043a\u043e\u0442\u043e\u0440\u044b\u0435",
    "\u0432\u0438\u0434\u0435\u043e",
    "\u043f\u043e\u0441\u0442",
    "\u0433\u0440\u0443\u043f\u043f\u0430",
    "\u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u043e",
    "\u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439",
    "\u0441\u043b\u0430\u0439\u0434",
    "\u0442\u0430\u043a\u0436\u0435",
    "\u0443\u0436\u0435",
    "\u0431\u043e\u043b\u044c\u0448\u0435",
    "\u043c\u0435\u043d\u044c\u0448\u0435",
    "\u043e\u0442\u0432\u0435\u0442",
    "\u0432\u0441\u0435\u0433\u0434\u0430",
}
_knowledge_store = VKKnowledgeStore()
_SUPPORTED_KB_FILE_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".yml",
    ".yaml",
    ".ini",
    ".log",
    ".xml",
    ".html",
    ".htm",
}

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


def _decode_uploaded_text(raw_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("latin-1", errors="replace")


def _normalize_source(source: str) -> str:
    value = source.strip()
    if value.startswith("https://") or value.startswith("http://"):
        value = value.split("vk.com/")[-1].strip("/")
    if "?" in value:
        value = value.split("?", 1)[0]
    if "#" in value:
        value = value.split("#", 1)[0]
    if value.startswith("public"):
        value = value.replace("public", "")
    if value.startswith("club"):
        value = value.replace("club", "")
    if value.startswith("@"):
        value = value[1:]
    return value


def _resolve_group_identity(vk_client: VKClient, access_token: str, source: str) -> tuple[str, int | None]:
    normalized = _normalize_source(source)
    if normalized.isdigit():
        return normalized, int(normalized)

    try:
        resolved = vk_client.resolve_screen_name(access_token, normalized)
    except VKOperationError as exc:
        message = str(exc).lower()
        if "failed to resolve 'api.vk.com'" in message or "nameresolutionerror" in message:
            raise HTTPException(
                status_code=503,
                detail="VK API is unavailable: DNS could not resolve api.vk.com",
            ) from exc
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    object_type = str(resolved.get("type") or "").lower()
    object_id = resolved.get("object_id")

    if object_type not in {"group", "page"}:
        raise HTTPException(
            status_code=400,
            detail=f"VK source resolved as '{object_type or 'unknown'}', not a group",
        )

    if not isinstance(object_id, int):
        raise HTTPException(status_code=404, detail="VK group not found")

    return normalized, object_id


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


def _should_use_public_fallback(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "method is unavailable with group auth" in message
        or "group authorization failed" in message
        or "access denied" in message
    )


def _public_post_id_to_int(post_id: str) -> int:
    value = (post_id or "").rsplit("_", 1)[-1]
    try:
        return int(value)
    except ValueError:
        return 0


def _search_vk_competitors(
    vk_client: VKClient,
    access_token: str,
    *,
    current_group_id: int,
    current_screen_name: str | None,
    current_name: str,
    current_activity: str | None,
    current_description: str | None,
    topic_clusters: list[dict],
    source_posts: list[dict] | None = None,
    ai_tags: list[str] | None = None,
    topic_labels: list[str] | None = None,
    limit: int = 5,
) -> list[dict]:
    source_posts = source_posts or []
    ai_tags = [tag.strip().lower() for tag in (ai_tags or []) if _is_query_term(tag)]
    topic_labels = [label.strip() for label in (topic_labels or []) if str(label).strip()]
    # Keep topical words from group name (e.g. "music", "fitness").
    # Exclude only direct brand slug tokens from screen_name.
    banned_name_terms = _brand_terms(current_screen_name or "")

    source_terms = _extract_cluster_terms(topic_clusters)
    source_tags = _extract_source_tags(source_posts, banned_terms=banned_name_terms)
    meta_tags = _extract_meta_tags(current_activity or "", current_description or "", current_screen_name or "")
    name_tags = [token for token in _tokenize_loose(current_name or "") if _is_query_word(token)]

    source_terms.update(source_tags)
    source_terms.update(meta_tags)
    source_terms.update(name_tags)
    source_terms.update(ai_tags)
    source_terms = {
        term for term in source_terms
        if _is_query_term(term) and term not in banned_name_terms
    }
    if len(source_terms) < 2:
        return []

    domain_terms = set(meta_tags[:5]) | set(ai_tags[:5])
    cluster_labels = topic_labels or [
        str(cluster.get("label") or "").strip()
        for cluster in topic_clusters[:5]
        if str(cluster.get("label") or "").strip()
    ]

    queries: list[str] = []
    for cluster in topic_clusters[:5]:
        terms = [
            str(term).strip().lower()
            for term in cluster.get("terms", [])
            if _is_query_term(str(term))
        ]
        if not terms:
            continue
        queries.extend(terms[:3])
        if len(terms) >= 2:
            queries.append(f"{terms[0]} {terms[1]}")

    for tag in source_tags[:8]:
        queries.append(tag)
    for tag in meta_tags[:5]:
        queries.append(tag)
        queries.append(f"{tag} vk")
    for tag in name_tags[:4]:
        queries.append(tag)
    for tag in ai_tags[:8]:
        queries.append(tag)

    source_terms_ranked = sorted(source_terms, key=lambda value: len(value), reverse=True)
    for idx in range(min(5, max(0, len(source_terms_ranked) - 1))):
        queries.append(f"{source_terms_ranked[idx]} {source_terms_ranked[idx + 1]}")

    dedup_queries: list[str] = []
    seen_queries: set[str] = set()
    for query in queries:
        normalized = " ".join(query.split()).strip().lower()
        if not _is_query_term(normalized):
            continue
        if normalized in seen_queries:
            continue
        seen_queries.add(normalized)
        dedup_queries.append(normalized)
        if len(dedup_queries) >= 18:
            break

    if not dedup_queries:
        return []

    candidates: dict[str, dict] = {}
    current_screen_name_l = (current_screen_name or "").lower()
    current_name_l = (current_name or "").lower()

    for query in dedup_queries:
        try:
            result = vk_client.call_api(
                "groups.search",
                access_token,
                q=query,
                count=25,
                sort=0,
                fields="members_count,activity,description,screen_name",
            )
            items = result.get("items", []) if isinstance(result, dict) else []
        except Exception:
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue
            gid = int(item.get("id", 0) or 0)
            if not gid or gid == current_group_id:
                continue

            name = str(item.get("name") or "").strip()
            screen_name = str(item.get("screen_name") or "").strip()
            if current_screen_name_l and screen_name.lower() == current_screen_name_l:
                continue
            if current_name_l and name.lower() == current_name_l:
                continue

            key = screen_name.lower() or str(gid)
            haystack = " ".join(
                part
                for part in [name, screen_name, str(item.get("activity") or ""), str(item.get("description") or "")]
                if part
            ).lower()

            entry = candidates.get(key)
            if entry is None:
                entry = {
                    "group_id": gid,
                    "name": name,
                    "screen_name": screen_name or None,
                    "members_count": item.get("members_count"),
                    "activity": item.get("activity"),
                    "_search_text": haystack,
                    "matched_by": [],
                    "_query_quality": 0.0,
                }
                candidates[key] = entry

            if query not in entry["matched_by"]:
                entry["matched_by"].append(query)
                entry["_query_quality"] = max(entry["_query_quality"], _query_quality(query, source_terms))

    def _merge_public_search_candidates(max_queries: int = 10, per_query: int = 8) -> None:
        for query in dedup_queries[:max_queries]:
            for item in search_public_groups(query, limit=per_query):
                if current_screen_name_l and item.screen_name.lower() == current_screen_name_l:
                    continue
                key = item.screen_name.lower()
                if key in candidates:
                    if query not in candidates[key]["matched_by"]:
                        candidates[key]["matched_by"].append(query)
                    candidates[key]["_query_quality"] = max(
                        float(candidates[key].get("_query_quality") or 0.0),
                        _query_quality(query, source_terms),
                    )
                    continue
                haystack = f"{item.name} {item.screen_name}".lower()
                candidates[key] = {
                    "group_id": abs(hash(item.screen_name)) % 1_000_000_000 + 1_000_000_000,
                    "name": item.name,
                    "screen_name": item.screen_name,
                    "members_count": None,
                    "activity": None,
                    "_search_text": haystack,
                    "matched_by": [query],
                    "_query_quality": _query_quality(query, source_terms),
                }

    if not candidates:
        _merge_public_search_candidates(max_queries=10, per_query=8)

    preliminary: list[dict] = []
    source_set = set(source_terms)
    source_activity_tokens = {
        token
        for token in _tokenize_loose(current_activity or "")
        if _is_query_word(token)
    }
    for candidate in candidates.values():
        candidate_tokens = {
            token
            for token in _tokenize_loose(candidate.get("_search_text") or "")
            if _is_query_word(token)
        }
        overlap = source_set & candidate_tokens
        if len(overlap) == 0:
            continue

        domain_overlap = len(domain_terms & candidate_tokens) if domain_terms else 0
        query_signal = float(candidate.get("_query_quality") or 0.0)
        if len(overlap) == 1 and domain_overlap == 0 and query_signal < 0.75:
            continue

        overlap_ratio = len(overlap) / max(1, len(source_set))
        member_signal = min(1.0, (int(candidate.get("members_count") or 0) / 2_000_000)) if candidate.get("members_count") else 0.15
        candidate_activity_tokens = {
            token
            for token in _tokenize_loose(str(candidate.get("activity") or ""))
            if _is_query_word(token)
        }
        activity_overlap = len(source_activity_tokens & candidate_activity_tokens)

        score = 0.20 + overlap_ratio * 0.50 + query_signal * 0.2 + member_signal * 0.08
        if domain_terms:
            score += min(0.1, domain_overlap * 0.03)
            if domain_overlap == 0:
                score *= 0.85
        if source_activity_tokens and candidate_activity_tokens:
            if activity_overlap == 0:
                score *= 0.78
            else:
                score += min(0.08, activity_overlap * 0.03)
        score = max(0.05, min(0.88, round(score, 3)))

        candidate["_overlap_terms"] = sorted(overlap)
        candidate["_score"] = score
        preliminary.append(candidate)

    if not preliminary:
        # Public-search content fallback:
        # for media groups, metadata overlap may be weak, so validate by post-topic overlap.
        _merge_public_search_candidates(max_queries=12, per_query=10)
        probe_candidates = list(candidates.values())[:24]
        for item in probe_candidates:
            screen_name = str(item.get("screen_name") or "").strip()
            if not screen_name:
                continue
            try:
                public_data = fetch_public_group_data(screen_name, limit=8)
                candidate_posts = [{"text": post.text} for post in public_data.posts if (post.text or "").strip()]
                if not candidate_posts:
                    continue
                candidate_terms = set(_extract_source_tags(candidate_posts, limit=24))
                overlap = source_set & candidate_terms
                if not overlap and domain_terms:
                    overlap = domain_terms & candidate_terms
                if not overlap:
                    continue

                overlap_ratio = len(overlap) / max(1, len(source_set))
                query_signal = float(item.get("_query_quality") or 0.0)
                score = max(0.31, min(0.90, round(0.24 + overlap_ratio * 0.62 + query_signal * 0.14, 3)))
                item["_overlap_terms"] = sorted(overlap)
                item["_score"] = score
                preliminary.append(item)
            except Exception:
                continue

        if not preliminary and candidates:
            # Query-hit fallback when metadata/content overlap is sparse.
            # Better return soft matches than empty list.
            for item in candidates.values():
                matched_by = [q for q in (item.get("matched_by") or []) if _is_query_term(q)]
                if not matched_by:
                    continue
                query_signal = float(item.get("_query_quality") or 0.0)
                member_signal = min(1.0, (int(item.get("members_count") or 0) / 2_000_000)) if item.get("members_count") else 0.12
                score = 0.22 + min(0.30, len(matched_by) * 0.06) + query_signal * 0.24 + member_signal * 0.10
                overlap = {
                    token
                    for query in matched_by
                    for token in _tokenize_loose(query)
                    if _is_query_word(token)
                }
                item["_overlap_terms"] = sorted(overlap)
                item["_score"] = round(max(0.24, min(0.74, score)), 3)
                preliminary.append(item)

            preliminary.sort(
                key=lambda item: (float(item.get("_score") or 0.0), len(item.get("matched_by") or []), int(item.get("members_count") or 0)),
                reverse=True,
            )
            preliminary = preliminary[: max(limit * 3, 10)]

        if not preliminary:
            return []

    preliminary.sort(
        key=lambda item: (float(item.get("_score") or 0.0), len(item.get("matched_by") or []), int(item.get("members_count") or 0)),
        reverse=True,
    )

    validated: list[dict] = []
    for index, item in enumerate(preliminary[:12]):
        final_score = float(item.get("_score") or 0.0)
        overlap_terms = set(item.get("_overlap_terms") or [])

        # Lightweight content validation for top candidates only.
        if index < 4 and item.get("screen_name"):
            try:
                public_data = fetch_public_group_data(str(item["screen_name"]), limit=5)
                candidate_posts = [{"text": post.text} for post in public_data.posts]
                candidate_terms = set(_extract_source_tags(candidate_posts, limit=18))
                content_overlap = source_set & candidate_terms
                if content_overlap:
                    overlap_terms |= content_overlap
                    content_ratio = len(content_overlap) / max(1, len(source_set))
                    final_score = min(0.92, round(final_score * 0.72 + content_ratio * 0.28 + 0.05, 3))
            except Exception:
                pass

        if final_score < 0.28:
            continue

        shared_topics = []
        for cluster in topic_clusters:
            cluster_terms = {
                str(term).strip().lower()
                for term in cluster.get("terms", [])
                if _is_query_term(str(term))
            }
            if cluster_terms and (cluster_terms & overlap_terms):
                label = str(cluster.get("label") or "").strip()
                if label and label not in shared_topics:
                    shared_topics.append(label)
        if not shared_topics:
            shared_topics = cluster_labels[:2]

        matched_by = [query for query in (item.get("matched_by") or []) if _is_query_term(query)][:10]
        if not matched_by:
            continue

        why_similar = (
            f"Найден по пересечению запросов: {', '.join(matched_by[:4])}. "
            f"Совпавшие теги: {', '.join(sorted(overlap_terms)[:6])}."
        )

        payload = {
            "group_id": int(item.get("group_id") or 0),
            "name": str(item.get("name") or ""),
            "screen_name": item.get("screen_name"),
            "members_count": item.get("members_count"),
            "activity": item.get("activity"),
            "matched_by": matched_by,
            "shared_topics": shared_topics[:3],
            "why_similar": why_similar,
            "similarity_score": round(final_score, 3),
        }
        validated.append(payload)

    validated.sort(
        key=lambda item: (float(item.get("similarity_score") or 0.0), len(item.get("matched_by") or []), int(item.get("members_count") or 0)),
        reverse=True,
    )

    if not validated:
        # Keep best preliminary matches instead of returning empty list.
        for item in preliminary[: max(3, limit)]:
            matched_by = [query for query in (item.get("matched_by") or []) if _is_query_term(query)][:10]
            if not matched_by:
                continue
            overlap_terms = sorted(set(item.get("_overlap_terms") or []))
            validated.append(
                {
                    "group_id": int(item.get("group_id") or 0),
                    "name": str(item.get("name") or ""),
                    "screen_name": item.get("screen_name"),
                    "members_count": item.get("members_count"),
                    "activity": item.get("activity"),
                    "matched_by": matched_by,
                    "shared_topics": cluster_labels[:2],
                    "why_similar": (
                        f"Найден по пересечению запросов: {', '.join(matched_by[:4])}. "
                        f"Совпавшие теги: {', '.join(overlap_terms[:6])}."
                    ),
                    "similarity_score": round(max(0.24, float(item.get('_score') or 0.24)), 3),
                }
            )

    if not validated:
        # Final fallback: direct public search by source name.
        source_name_query = " ".join((current_name or "").split())
        for item in search_public_groups(source_name_query, limit=max(3, limit)):
            screen_name = (item.screen_name or "").strip().lower()
            if not screen_name:
                continue
            if current_screen_name_l and screen_name == current_screen_name_l:
                continue
            validated.append(
                {
                    "group_id": abs(hash(item.screen_name)) % 1_000_000_000 + 1_000_000_000,
                    "name": item.name,
                    "screen_name": item.screen_name,
                    "members_count": None,
                    "activity": None,
                    "matched_by": [source_name_query],
                    "shared_topics": cluster_labels[:2],
                    "why_similar": (
                        f"Найден через VK search по названию источника: {source_name_query}."
                    ),
                    "similarity_score": 0.24,
                }
            )

    result: list[dict] = []
    seen_names: set[str] = set()
    for item in validated:
        name_key = (str(item.get("name") or "").strip().lower(), str(item.get("screen_name") or "").strip().lower())
        if name_key in seen_names:
            continue
        seen_names.add(name_key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _extract_cluster_terms(topic_clusters: list[dict]) -> set[str]:
    terms: set[str] = set()
    for cluster in topic_clusters:
        for term in cluster.get("terms", []) or []:
            normalized = str(term).strip().lower()
            if not normalized or not _is_query_term(normalized):
                continue
            terms.add(normalized)
            parts = [part for part in normalized.split() if _is_query_word(part)]
            terms.update(parts)
    return terms


def _extract_source_tags(posts: list[dict], limit: int = 10, banned_terms: set[str] | None = None) -> list[str]:
    banned_terms = banned_terms or set()
    token_tf: Counter[str] = Counter()
    token_df: Counter[str] = Counter()
    phrase_tf: Counter[str] = Counter()
    phrase_df: Counter[str] = Counter()

    for post in posts:
        text = str(post.get("text") or "")
        tokens = [token for token in _tokenize_loose(text) if len(token) >= 4]
        tokens = [token.lower() for token in tokens if _is_query_word(token) and token.lower() not in banned_terms]
        if not tokens:
            continue

        uniq_tokens = set(tokens)
        for token in tokens:
            token_tf[token] += 1
        for token in uniq_tokens:
            token_df[token] += 1

        uniq_phrases: set[str] = set()
        for idx in range(len(tokens) - 1):
            phrase = f"{tokens[idx]} {tokens[idx + 1]}"
            if _is_query_term(phrase):
                phrase_tf[phrase] += 1
                uniq_phrases.add(phrase)
        for phrase in uniq_phrases:
            phrase_df[phrase] += 1

    total_docs = max(1, len(posts))

    scored: list[tuple[str, float]] = []
    for token, tf in token_tf.items():
        df = token_df.get(token, 1)
        if total_docs >= 6 and df < 2:
            continue
        score = tf * (1.0 + (1.0 / max(1, df)))
        scored.append((token, score))

    for phrase, tf in phrase_tf.items():
        df = phrase_df.get(phrase, 1)
        if total_docs >= 6 and df < 2:
            continue
        score = tf * 1.25
        scored.append((phrase, score))

    scored.sort(key=lambda item: (item[1], len(item[0])), reverse=True)

    tags: list[str] = []
    for term, _ in scored:
        if term in tags:
            continue
        if any(term in existing or existing in term for existing in tags):
            continue
        tags.append(term)
        if len(tags) >= limit:
            break

    return tags


def _brand_terms(*values: str) -> set[str]:
    terms: set[str] = set()
    for value in values:
        for token in _tokenize_loose(value):
            if len(token) >= 4:
                terms.add(token)
    return terms


def _extract_meta_tags(activity: str, description: str, name: str, limit: int = 8) -> list[str]:
    brand = _brand_terms(name)
    text = " ".join(part for part in [activity, description] if part)
    tokens = [token for token in _tokenize_loose(text) if _is_query_word(token) and token not in brand]

    counter: Counter[str] = Counter(tokens)
    for token in _tokenize_loose(activity):
        if _is_query_word(token) and token not in brand:
            counter[token] += 3

    # Useful phrases from description (e.g. "???? ???????", "?????? ???").
    seq = [token for token in _tokenize_loose(description or "") if _is_query_word(token) and token not in brand]
    for idx in range(len(seq) - 1):
        phrase = f"{seq[idx]} {seq[idx + 1]}"
        if _is_query_term(phrase):
            counter[phrase] += 2

    tags: list[str] = []
    for term, _ in counter.most_common(limit * 3):
        if term in tags:
            continue
        if any(term in existing or existing in term for existing in tags):
            continue
        tags.append(term)
        if len(tags) >= limit:
            break
    return tags


def _extract_ai_search_tags(ai: VKGroupAIInsights, limit: int = 14) -> list[str]:
    counters: Counter[str] = Counter()
    texts = list(ai.audience_interests or []) + list(ai.potential_competitors or []) + [ai.summary or ""]
    for text in texts:
        tokens = [token for token in _tokenize_loose(str(text or "").lower()) if _is_query_word(token)]
        for token in tokens:
            counters[token] += 1
        for idx in range(len(tokens) - 1):
            phrase = f"{tokens[idx]} {tokens[idx + 1]}"
            if _is_query_term(phrase):
                counters[phrase] += 2

    tags: list[str] = []
    for term, _ in counters.most_common(limit * 3):
        if term in tags:
            continue
        if any(term in existing or existing in term for existing in tags):
            continue
        tags.append(term)
        if len(tags) >= limit:
            break
    return tags


def _extract_ai_topic_labels(ai: VKGroupAIInsights, limit: int = 4) -> list[str]:
    labels: list[str] = []
    for raw in list(ai.audience_interests or [])[:limit]:
        label = str(raw or "").strip()
        if not label:
            continue
        if ":" in label:
            label = label.split(":", 1)[0].strip()
        label = " ".join(label.split())
        if len(label) > 56:
            label = label[:56].rstrip(" ,.;:")
        if label and label not in labels:
            labels.append(label)
    return labels


def _query_quality(query: str, source_terms: set[str]) -> float:
    words = [word for word in _tokenize_loose(query) if _is_query_word(word)]
    if not words:
        return 0.0
    overlap = len(set(words) & source_terms)
    return min(1.0, overlap / max(1, len(set(words))))


def _is_query_term(text: str) -> bool:
    words = [word.strip().lower() for word in _tokenize_loose(str(text or "")) if word.strip()]
    if not words:
        return False
    meaningful = [word for word in words if _is_query_word(word)]
    if not meaningful:
        return False
    if len(words) >= 2 and len(meaningful) < 2:
        return len(meaningful) == 1 and any(ch.isdigit() for ch in meaningful[0])
    return True


def _is_query_word(word: str) -> bool:
    value = str(word or "").strip().lower()
    if len(value) < 4:
        if len(value) < 3 or not (any(ch.isalpha() for ch in value) and any(ch.isdigit() for ch in value)):
            return False
    if value in _WEAK_QUERY_WORDS:
        return False
    if value in STOPWORDS:
        return False
    if any(stem in value for stem in _MONTH_QUERY_STEMS):
        return False
    if _looks_like_verb(value):
        return False
    if _looks_like_noise_slug(value):
        return False
    return any(ch.isalpha() for ch in value)


def _looks_like_noise_slug(word: str) -> bool:
    value = word.lower()
    if not value.isascii() or len(value) < 6:
        return False
    suffixes = ("news", "video", "videos", "media", "music", "blog")
    return any(value.endswith(suffix) and value != suffix for suffix in suffixes)


def _tokenize_loose(text: str) -> list[str]:
    text = str(text or "").lower()
    tokens: list[str] = []
    buf: list[str] = []
    for ch in text:
        if ch.isalnum() or ch in {"_", "-"}:
            buf.append(ch)
        else:
            if buf:
                token = "".join(buf).strip("-_")
                if len(token) >= 2:
                    tokens.append(token)
                buf = []
    if buf:
        token = "".join(buf).strip("-_")
        if len(token) >= 2:
            tokens.append(token)
    return tokens


def _looks_like_verb(token: str) -> bool:
    value = token.lower()
    verb_suffixes = (
        "\u0442\u044c\u0441\u044f",
        "\u0438\u0442\u044c\u0441\u044f",
        "\u0430\u0442\u044c",
        "\u044f\u0442\u044c",
        "\u0435\u0442\u044c",
        "\u043e\u0432\u0430\u0442\u044c",
        "\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
        "\u0435\u0448\u044c",
        "\u0435\u0442\u0435",
        "\u0435\u043c",
        "\u044e\u0442",
        "\u0443\u0442",
        "\u0438\u0442",
        "\u0430\u0442",
        "\u044f\u0442",
        "\u0438\u043b",
        "\u0438\u043b\u0430",
        "\u0438\u043b\u0438",
        "\u0430\u043b",
        "\u0430\u043b\u0430",
        "\u0430\u043b\u0438",
    )
    return any(value.endswith(suffix) for suffix in verb_suffixes)


def _is_group_auth_restriction(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "method is unavailable with group auth" in message
        or "group authorization failed" in message
    )


def _build_audience_profile(ai: VKGroupAIInsights, metrics: VKGroupMetricsResponse, topic_clusters: list[dict]) -> dict:
    content_preferences = []
    if topic_clusters:
        content_preferences.append(f"Лучше всего заходят темы: {', '.join(cluster['label'] for cluster in topic_clusters[:2])}")
    if metrics.average_views >= 300:
        content_preferences.append("Контент собирает заметный охват даже в публичном режиме просмотра")
    if metrics.average_comments >= 10:
        content_preferences.append("Лучше работают посты, которые провоцируют обсуждение в комментариях")
    if not content_preferences:
        content_preferences.append("Нужно больше данных, чтобы точно определить предпочитаемые форматы контента")

    engagement_style = []
    if metrics.average_comments >= 10:
        engagement_style.append("Аудитория активно спорит и обсуждает инфоповоды в комментариях")
    if metrics.average_likes >= 50:
        engagement_style.append("Реакции на посты стабильные, особенно на новостные и событийные темы")
    if metrics.posts_per_day >= 2:
        engagement_style.append("Лента потребляется быстро, аудитория привыкла к плотному новостному ритму")
    if not engagement_style:
        engagement_style.append("Вовлеченность видна частично, потому что часть метрик ограничена публичным доступом")

    return {
        "interests": ai.audience_interests,
        "age_segments": ai.audience_age,
        "activity_profile": ai.audience_activity,
        "content_preferences": content_preferences[:3],
        "engagement_style": engagement_style[:3],
        "summary": ai.summary,
    }

def _build_recommendations(
    metrics: VKGroupMetricsResponse,
    topic_clusters: list[dict],
    competitors_found: list[dict],
) -> list[dict]:
    recommendations = []

    if topic_clusters:
        top_cluster = topic_clusters[0]
        recommendations.append(
            {
                "title": "Усиливать главную тему",
                "action": f"Сделать контент-серию вокруг темы '{top_cluster.get('label')}' и её термов: {', '.join(top_cluster.get('terms', [])[:3])}.",
                "rationale": "Главный кластер самый плотный, значит аудитория уже реагирует на этот тематический сигнал.",
            }
        )

    if metrics.average_comments >= 10:
        recommendations.append(
            {
                "title": "Давать поводы для спора",
                "action": "Публиковать посты с вопросом, мнением редакции или сравнением патчей и игроков, чтобы усиливать комментарии.",
                "rationale": "Среднее число комментариев уже заметное, значит аудитория склонна обсуждать спорные и новостные темы.",
            }
        )
    else:
        recommendations.append(
            {
                "title": "Поднимать дискуссию",
                "action": "Добавлять CTA в конце постов: вопрос, прогноз, голосование или короткий тезис для обсуждения.",
                "rationale": "Комментарии можно нарастить за счёт более явного приглашения к обсуждению.",
            }
        )

    if competitors_found:
        top_competitor = competitors_found[0]
        recommendations.append(
            {
                "title": "Сравнить контент с конкурентом",
                "action": f"Разобрать контент паблика '{top_competitor.get('name')}' по темам и частоте публикаций.",
                "rationale": "Это ближайший найденный тематический конкурент, и его можно использовать как ориентир по упаковке тем.",
            }
        )

    return recommendations[:3]

def _render_group_report_png(report: VKGroupAnalyzeResponse) -> bytes:
    if plt is None:
        raise RuntimeError("matplotlib is not installed")

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.patch.set_facecolor("white")
    fig.suptitle(f"VK Analytics Report: {report.source.name}", fontsize=16, fontweight="bold")

    metric_names = ["Views", "Likes", "Comments", "Reposts"]
    metric_values = [
        report.metrics.average_views,
        report.metrics.average_likes,
        report.metrics.average_comments,
        report.metrics.average_reposts,
    ]
    ax = axes[0][0]
    bars = ax.bar(metric_names, metric_values, color=["#3b82f6", "#22c55e", "#f59e0b", "#ef4444"])
    ax.set_title("Average Post Metrics")
    ax.set_ylabel("Count")
    ax.grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, metric_values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + max(metric_values + [1]) * 0.02, str(value), ha="center", va="bottom", fontsize=9)

    ax = axes[0][1]
    cluster_labels = [cluster.label[:26] for cluster in report.topic_clusters[:5]]
    cluster_sizes = [cluster.size for cluster in report.topic_clusters[:5]]
    if cluster_labels:
        ax.barh(cluster_labels, cluster_sizes, color="#8b5cf6")
        ax.invert_yaxis()
    ax.set_title("Topic Cluster Sizes")
    ax.set_xlabel("Posts in cluster")
    ax.grid(axis="x", alpha=0.25)

    ax = axes[1][0]
    competitor_labels = [item.name[:24] for item in report.competitors_found[:5]]
    competitor_scores = [item.similarity_score for item in report.competitors_found[:5]]
    if competitor_labels:
        ax.bar(competitor_labels, competitor_scores, color="#14b8a6")
        ax.set_ylim(0, 1)
        ax.tick_params(axis="x", rotation=20)
    ax.set_title("Competitor Similarity")
    ax.set_ylabel("Score")
    ax.grid(axis="y", alpha=0.25)

    ax = axes[1][1]
    ax.axis("off")
    summary_lines = [
        f"Source: {report.source.screen_name or report.source.name}",
        f"Posts analyzed: {report.metrics.total_posts_analyzed}",
        f"Posts/day: {report.metrics.posts_per_day}",
        f"Top interest: {report.audience_profile.interests[0] if report.audience_profile.interests else 'n/a'}",
        f"Audience age: {', '.join(report.audience_profile.age_segments[:2]) or 'n/a'}",
        f"AI status: {report.ai_status.message[:120]}",
    ]
    ax.text(
        0.0,
        1.0,
        "\n".join(summary_lines),
        va="top",
        ha="left",
        fontsize=10,
        wrap=True,
        family="DejaVu Sans",
    )
    ax.set_title("Summary")

    plt.tight_layout(rect=(0, 0, 1, 0.96))
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()


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


@router.get(
    "/knowledge",
    response_model=VKKnowledgeBaseListResponse,
    summary="List uploaded VK knowledge bases",
)
def vk_list_knowledge_bases():
    items = _knowledge_store.list_items()
    return VKKnowledgeBaseListResponse(
        items=[VKKnowledgeBaseItemResponse(**item) for item in items],
    )


@router.post(
    "/knowledge/upload",
    response_model=VKKnowledgeBaseUploadResponse,
    summary="Upload or update VK knowledge base",
)
def vk_upload_knowledge_base(payload: VKKnowledgeBaseUploadRequest):
    active = _knowledge_store.get_active()
    target_kb_id = str(active.get("id") or "") if active else None
    try:
        entry = _knowledge_store.upsert(
            name=payload.name,
            content=payload.content,
            language=payload.language,
            knowledge_base_id=target_kb_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    item = VKKnowledgeBaseItemResponse(
        id=str(entry.get("id") or ""),
        name=str(entry.get("name") or ""),
        language=str(entry.get("language") or "ru"),
        content_length=len(str(entry.get("content") or "")),
        created_at=entry.get("created_at"),
        updated_at=entry.get("updated_at"),
        is_active=True,
    )
    return VKKnowledgeBaseUploadResponse(item=item)


@router.post(
    "/knowledge/upload-file",
    response_model=VKKnowledgeBaseUploadResponse,
    summary="Upload file into SQLite knowledge base",
)
def vk_upload_knowledge_file(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    language: str = Form(default="ru"),
):
    filename = (file.filename or "").strip()
    extension = Path(filename).suffix.lower()
    if extension not in _SUPPORTED_KB_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. Allowed: "
                + ", ".join(sorted(_SUPPORTED_KB_FILE_EXTENSIONS))
            ),
        )

    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    text_content = _decode_uploaded_text(raw).strip()
    if not text_content:
        raise HTTPException(status_code=400, detail="Uploaded file has no readable text")

    active = _knowledge_store.get_active()
    target_kb_id = str(active.get("id") or "") if active else None
    try:
        entry = _knowledge_store.add_file(
            filename=filename,
            content=text_content,
            mime_type=file.content_type,
            language=language,
            name=name,
            knowledge_base_id=target_kb_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    item = VKKnowledgeBaseItemResponse(
        id=str(entry.get("id") or ""),
        name=str(entry.get("name") or ""),
        language=str(entry.get("language") or "ru"),
        content_length=len(str(entry.get("content") or "")),
        created_at=entry.get("created_at"),
        updated_at=entry.get("updated_at"),
        is_active=bool(entry.get("is_active")),
    )
    return VKKnowledgeBaseUploadResponse(item=item)


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
    summary="Generate VK post with GigaChat (optional publish)",
)
def vk_generate_post(
    payload: VKAIPostRequest,
    publisher: VKPublisher = Depends(get_vk_publisher),
    vk_client: VKClient = Depends(get_vk_client),
):
    if not is_gigachat_configured():
        raise HTTPException(status_code=400, detail="GigaChat is not configured")

    access_tokens = _resolve_access_tokens()
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
    if selected_kb:
        kb_excerpt = _knowledge_store.build_excerpt(str(selected_kb.get("content") or ""), max_chars=5000)
        kb_id = str(selected_kb.get("id") or "")
        kb_name = str(selected_kb.get("name") or "")
        context["knowledge_base"] = {
            "id": kb_id,
            "name": kb_name,
            "language": str(selected_kb.get("language") or "ru"),
            "content_excerpt": kb_excerpt,
        }

    client = GigaChatVKClient(load_gigachat_settings())
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
        raise HTTPException(status_code=502, detail=f"GigaChat error: {exc}") from exc

    text = generated.text

    if payload.publish:
        result = None
        last_error: Exception | None = None
        media_error: Exception | None = None
        try:
            if generated.content_type == "image":
                image_prompt = (generated.image_prompt or "").strip() or text or payload.prompt
                image_bytes, image_mime_type, _ = client.generate_image(
                    prompt=image_prompt,
                    language=payload.language,
                    theme=payload.theme,
                    tone=payload.tone,
                    knowledge_base=kb_excerpt,
                )
            elif generated.content_type == "video":
                video_prompt = (generated.video_script or "").strip() or text or payload.prompt
                video_bytes, video_mime_type, _ = client.generate_video(
                    prompt=video_prompt,
                    language=payload.language,
                    theme=payload.theme,
                    tone=payload.tone,
                    knowledge_base=kb_excerpt,
                )

            for token in access_tokens:
                try:
                    if generated.content_type == "image":
                        result = publisher.publish_with_generated_image(
                            access_token=token,
                            group_id=group_id or 0,
                            message=text,
                            image_bytes=image_bytes,
                            image_mime_type=image_mime_type,
                        )
                    elif generated.content_type == "video":
                        result = publisher.publish_with_generated_video(
                            access_token=token,
                            group_id=group_id or 0,
                            message=text,
                            video_bytes=video_bytes,
                            video_mime_type=video_mime_type,
                            video_title=(payload.theme or "Generated video").strip()[:80] or "Generated video",
                        )
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
        return VKAIPostResponse(
            text=text,
            published=True,
            post_id=result.post_id,
            owner_id=result.owner_id,
            char_count=char_count,
            word_count=word_count,
            token_estimate=token_estimate,
            token_estimate_method="chars/4",
            content_type=generated.content_type,
            theme=payload.theme,
            tone=payload.tone,
            story_frames=generated.story_frames,
            image_prompt=generated.image_prompt,
            video_script=generated.video_script,
            knowledge_base_id=kb_id,
            knowledge_base_name=kb_name,
        )

    char_count = len(text)
    word_count = len([w for w in text.split() if w.strip()])
    token_estimate = max(1, int(round(char_count / 4)))
    return VKAIPostResponse(
        text=text,
        published=False,
        post_id=None,
        owner_id=None,
        char_count=char_count,
        word_count=word_count,
        token_estimate=token_estimate,
        token_estimate_method="chars/4",
        content_type=generated.content_type,
        theme=payload.theme,
        tone=payload.tone,
        story_frames=generated.story_frames,
        image_prompt=generated.image_prompt,
        video_script=generated.video_script,
        knowledge_base_id=kb_id,
        knowledge_base_name=kb_name,
    )


@router.post(
    "/group/analyze",
    response_model=VKGroupAnalyzeResponse,
    summary="Analyze VK group with GigaChat",
)
def vk_group_analyze(
    payload: VKGroupAnalyzeRequest,
    vk_client: VKClient = Depends(get_vk_client),
):
    access_token = _resolve_access_token()
    if not access_token:
        raise HTTPException(status_code=401, detail="VK access_token is required")

    normalized, resolved_group_id = _resolve_group_identity(vk_client, access_token, payload.source)
    try:
        group_info = vk_client.call_api(
            "groups.getById",
            access_token,
            group_id=str(resolved_group_id or normalized),
            fields="members_count,screen_name,name,description,activity,site",
        )
    except VKOperationError as exc:
        message = str(exc).lower()
        if "failed to resolve 'api.vk.com'" in message or "nameresolutionerror" in message:
            raise HTTPException(
                status_code=503,
                detail="VK API is unavailable: DNS could not resolve api.vk.com",
            ) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if isinstance(group_info, dict):
        if "error" in group_info:
            message = group_info.get("error", {}).get("error_msg") or "VK API error"
            raise HTTPException(status_code=400, detail=message)
        if "groups" in group_info and isinstance(group_info.get("groups"), list):
            group_info = group_info.get("groups")
        if "response" in group_info:
            response_payload = group_info.get("response")
            if isinstance(response_payload, dict) and "groups" in response_payload:
                group_info = response_payload.get("groups")
            else:
                group_info = response_payload

    if not isinstance(group_info, list) or not group_info:
        raise HTTPException(status_code=404, detail="VK group not found")
    group = group_info[0]
    group_id = int(group.get("id"))

    posts = []
    metrics_views: list[int] = []
    metrics_likes: list[int] = []
    metrics_comments: list[int] = []
    metrics_reposts: list[int] = []
    post_dates: list[int] = []
    top_posts = []
    limitations = []

    try:
        wall = vk_client.call_api(
            "wall.get",
            access_token,
            owner_id=-abs(group_id),
            count=max(1, min(payload.post_limit, 100)),
            filter="owner",
            extended=0,
        )

        items = wall.get("items", []) if isinstance(wall, dict) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = (item.get("text") or "").strip()
            views = int(item.get("views", {}).get("count", 0) or 0)
            likes = int(item.get("likes", {}).get("count", 0) or 0)
            comments = int(item.get("comments", {}).get("count", 0) or 0)
            reposts = int(item.get("reposts", {}).get("count", 0) or 0)
            date = int(item.get("date", 0) or 0)

            metrics_views.append(views)
            metrics_likes.append(likes)
            metrics_comments.append(comments)
            metrics_reposts.append(reposts)
            if date:
                post_dates.append(date)

            posts.append(
                {
                    "text": text[:1200],
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "reposts": reposts,
                    "date": date,
                }
            )
            top_posts.append(
                {
                    "post_id": int(item.get("id", 0) or 0),
                    "date": date,
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "reposts": reposts,
                }
            )
    except VKOperationError as exc:
        message = str(exc).lower()
        if "failed to resolve 'api.vk.com'" in message or "nameresolutionerror" in message:
            raise HTTPException(
                status_code=503,
                detail="VK API is unavailable: DNS could not resolve api.vk.com",
            ) from exc
        if not _should_use_public_fallback(exc):
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            public_group = fetch_public_group_data(normalized, group_id=group_id, limit=payload.post_limit)
            if public_group.name and public_group.name != normalized:
                group["name"] = public_group.name
            group["screen_name"] = public_group.screen_name or group.get("screen_name")
            posts = [
                {
                    "text": item.text[:1200],
                    "views": item.views,
                    "likes": item.likes,
                    "comments": item.comments,
                    "reposts": item.reposts,
                    "date": item.timestamp,
                }
                for item in public_group.posts
            ]
            metrics_views = [item.views for item in public_group.posts if item.views >= 10]
            metrics_likes = [item.likes for item in public_group.posts if item.likes > 0]
            metrics_comments = [item.comments for item in public_group.posts if item.comments > 0]
            metrics_reposts = [item.reposts for item in public_group.posts if item.reposts > 0]
            post_dates = [item.timestamp for item in public_group.posts if item.timestamp > 0]
            top_posts = [
                {
                    "post_id": _public_post_id_to_int(item.post_id),
                    "date": item.timestamp,
                    "views": item.views,
                    "likes": item.likes,
                    "comments": item.comments,
                    "reposts": item.reposts,
                }
                for item in public_group.posts[:5]
            ]
            limitations.append("Used public page fallback because VK API wall access is unavailable for group token.")
            if not posts:
                limitations.append("VK public page loaded, but posts were not available in rendered DOM.")
        except Exception as fallback_exc:
            posts = []
            top_posts = []
            limitations.append(f"Public fallback failed: {fallback_exc}")

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

    local_ai_payload, local_ai_status = build_local_vk_insights(
        group_name=group.get("name", ""),
        screen_name=group.get("screen_name") or normalized,
        posts=posts[: max(1, min(len(posts), 50))],
        metrics=metrics.model_dump(),
    )
    ai_insights = VKGroupAIInsights(**local_ai_payload)
    ai_status = local_ai_status

    if is_gigachat_configured():
        settings = load_gigachat_settings()
        client = GigaChatVKClient(settings)
        try:
            ai_result = client.analyze_group(
                payload={
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
                },
                language=payload.language,
            )
            ai_insights = VKGroupAIInsights(
                audience_interests=ai_result.audience_interests,
                audience_age=ai_result.audience_age,
                audience_activity=ai_result.audience_activity,
                potential_competitors=ai_result.potential_competitors,
                summary=ai_result.summary,
                limitations=ai_result.limitations,
            )
            ai_status = {
                "enabled": True,
                "available": True,
                "enhanced": True,
                "provider": "gigachat",
                "model": settings.model,
                "auth_mode": "auth_key" if settings.authorization_key else "credentials",
                "message": "GigaChat analysis completed",
            }
        except Exception as exc:
            ai_status = {
                "enabled": True,
                "available": False,
                "enhanced": False,
                "provider": "gigachat",
                "model": None,
                "auth_mode": None,
                "message": f"GigaChat unavailable, used local analysis instead: {str(exc)[:240]}",
            }

    # Clusters are disabled in API response: competitor search now relies on AI tags.
    topic_clusters: list[dict] = []
    ai_tags = _extract_ai_search_tags(ai_insights, limit=16)
    ai_topic_labels = _extract_ai_topic_labels(ai_insights, limit=4)

    competitors_found: list[dict] = []
    for token in _resolve_access_tokens():
        try:
            competitors_found = _search_vk_competitors(
                vk_client,
                token,
                current_group_id=group_id,
                current_screen_name=group.get("screen_name"),
                current_name=group.get("name", ""),
                current_activity=group.get("activity"),
                current_description=group.get("description"),
                topic_clusters=[],
                source_posts=posts,
                ai_tags=ai_tags,
                topic_labels=ai_topic_labels,
                limit=5,
            )
            if competitors_found:
                break
        except Exception:
            continue

    audience_profile = _build_audience_profile(ai_insights, metrics, topic_clusters)
    recommendations = _build_recommendations(metrics, topic_clusters, competitors_found)

    return VKGroupAnalyzeResponse(
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
        topic_clusters=[VKTopicClusterResponse(**cluster) for cluster in topic_clusters],
        competitors_found=[VKCompetitorFoundResponse(**item) for item in competitors_found],
        recommendations=[VKAnalyticsRecommendationResponse(**item) for item in recommendations],
        ai_status=ai_status,
    )


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






