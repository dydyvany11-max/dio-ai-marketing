import json
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

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
    VKPublishRequest,
    VKPublishResponse,
    VKRAGChunkUsedResponse,
)
from src.api.services.errors import VKAuthorizationError, VKOperationError
from src.api.services.vk_analysis_helpers import (
    _build_audience_profile,
    _extract_ai_search_tags,
    _extract_ai_topic_labels,
    _is_query_term,
    _is_query_word,
    _is_group_auth_restriction,
    _render_group_report_png,
    _search_vk_competitors,
)
from src.api.services.vk_ai import GigaChatVKClient
from src.api.services.vk_client import VKClient
from src.api.services.vk_knowledge import VKKnowledgeStore
from src.api.services.vk_local_analysis import build_local_vk_insights
from src.api.services.vk_public import (
    fetch_public_group_data,
    has_vk_browser_profile,
    launch_vk_browser_login,
    vk_browser_profile_dir,
)
from src.api.services.vk_publisher import VKPublisher, VKPublishRequest as VKPublishPayload

router = APIRouter(prefix="/vk", tags=["VK"])
_knowledge_store = VKKnowledgeStore()

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
            knowledge_chunks_used=len(kb_snippets) if kb_snippets else None,
            knowledge_chunks=kb_chunks_payload,
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
        knowledge_chunks_used=len(kb_snippets) if kb_snippets else None,
        knowledge_chunks=kb_chunks_payload,
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
            metrics_views = [item.views for item in public_group.posts if 10 <= item.views <= 50_000_000]
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
    recommendations: list[dict] = []

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

    ai_tags = _extract_ai_search_tags(ai_insights, limit=16)
    if not ai_tags:
        ai_tags = [
            str(tag).strip().lower()
            for tag in (local_ai_payload.get("search_tags") or [])
            if _is_query_term(str(tag))
        ]
    if ai_tags:
        ai_insights.search_tags = ai_tags
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

    audience_profile = _build_audience_profile(ai_insights, metrics)

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






