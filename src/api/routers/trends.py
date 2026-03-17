from fastapi import APIRouter

from src.api.config import load_trends_settings, is_gigachat_configured, load_gigachat_settings
from src.api.services.trends_collectors import collect_from_sources, parse_sources
from src.api.services.trends_db import (
    add_source,
    clear_trends,
    init_db,
    list_recent_articles,
    list_sources,
    list_trends,
    set_source_enabled,
    store_articles,
)
from src.api.services.trends_engine import compute_trends, update_term_counts, quick_trends_from_articles
from src.api.services.trends_topics import build_topics_with_meta
from src.api.services.trends_ai import GigaChatTrendsLabeler
from src.api.schemas import (
    TrendRefreshResponse,
    TrendSourceCreateRequest,
    TrendSourceListResponse,
    TrendSourceUpdateRequest,
)

router = APIRouter(prefix="/trends", tags=["Trends"])


@router.get("/sources", response_model=TrendSourceListResponse)
def trends_sources():
    settings = load_trends_settings()
    rows = list_sources(settings.db_path, enabled_only=False)
    return TrendSourceListResponse(items=rows)


@router.post("/sources", response_model=TrendSourceListResponse)
def trends_sources_add(payload: TrendSourceCreateRequest):
    settings = load_trends_settings()
    init_db(settings.db_path)
    add_source(
        settings.db_path,
        name=payload.name,
        url=payload.url,
        source_type=payload.type,
        enabled=payload.enabled,
        meta_json=payload.meta_json,
    )
    rows = list_sources(settings.db_path, enabled_only=False)
    return TrendSourceListResponse(items=rows)


@router.post("/sources/{source_id}")
def trends_sources_update(source_id: int, payload: TrendSourceUpdateRequest):
    settings = load_trends_settings()
    set_source_enabled(settings.db_path, source_id=source_id, enabled=payload.enabled)
    return {"ok": True}


@router.post("/reset")
def trends_reset():
    settings = load_trends_settings()
    clear_trends(settings.db_path)
    return {"ok": True}


@router.post("/refresh", response_model=TrendRefreshResponse)
def trends_refresh():
    settings = load_trends_settings()
    init_db(settings.db_path)
    sources = parse_sources(list_sources(settings.db_path, enabled_only=True))

    articles = collect_from_sources(
        sources,
        newsapi_key=settings.newsapi_key,
        newsapi_sources=settings.newsapi_sources,
        gdelt_query=settings.gdelt_query,
    )
    inserted = store_articles(settings.db_path, articles)

    recent = list_recent_articles(settings.db_path, limit=500)
    update_term_counts(settings.db_path, recent)
    trends = compute_trends(settings.db_path, window_hours=settings.window_hours, max_terms=settings.max_terms)
    if not trends:
        trends = quick_trends_from_articles(recent, max_terms=settings.max_terms)
        if trends:
            from src.api.services.trends_db import save_trends
            save_trends(settings.db_path, trends)

    return TrendRefreshResponse(inserted=inserted, trends=trends)


@router.get("/report")
def trends_report(
    limit: int = 10,
    method: str = "auto",
    k: int = 8,
    eps: float = 0.35,
    min_samples: int = 3,
):
    settings = load_trends_settings()
    trends = list_trends(settings.db_path, limit=limit)
    articles = list_recent_articles(settings.db_path, limit=500)
    topics, meta = build_topics_with_meta(
        articles,
        max_topics=limit,
        method=method,
        n_clusters=k,
        eps=eps,
        min_samples=min_samples,
    )

    ai = {"enabled": False, "available": False, "message": "GigaChat is not configured"}
    if is_gigachat_configured() and topics:
        try:
            labeler = GigaChatTrendsLabeler(load_gigachat_settings())
            topics = labeler.label_clusters(topics)
            ai = {"enabled": True, "available": True, "message": "GigaChat labeled topics"}
        except Exception as exc:
            ai = {"enabled": True, "available": False, "message": f"GigaChat error: {exc}"}
    if topics:
        for topic in topics:
            if "label" not in topic or not topic.get("label"):
                terms = topic.get("terms", [])[:4]
                if terms:
                    topic["label"] = ", ".join(terms)

    summary = []
    for trend in trends:
        term = trend["term"]
        titles = []
        sources = []
        for art in articles:
            content = (art.get("title") or "") + " " + (art.get("content") or "")
            if term in (content or "").lower():
                if art.get("title"):
                    titles.append(art.get("title"))
                if art.get("source"):
                    sources.append(art.get("source"))
            if len(titles) >= 3:
                break
        summary.append(
            {
                "term": term,
                "score": trend["score"],
                "growth": trend["growth"],
                "sample_titles": titles[:3],
                "top_sources": list(dict.fromkeys(sources))[:3],
            }
        )

    return {
        "sources": list_sources(settings.db_path, enabled_only=False),
        "recent_articles_count": len(articles),
        "trends": trends,
        "summary": summary,
        "topics": topics,
        "topics_meta": meta,
        "ai": ai,
    }
