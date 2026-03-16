from fastapi import APIRouter, HTTPException

from src.api.config import load_trends_settings
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
from src.api.services.trends_topics import build_topics
from src.api.schemas import (
    TrendItem,
    TrendArticleListResponse,
    TrendListResponse,
    TrendRefreshResponse,
    TrendSourceCreateRequest,
    TrendSourceListResponse,
    TrendSourceUpdateRequest,
    TrendTopicListResponse,
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




@router.get("/summary")
def trends_summary(limit: int = 10):
    settings = load_trends_settings()
    items = list_trends(settings.db_path, limit=limit)
    articles = list_recent_articles(settings.db_path, limit=500)

    # build quick lookup of titles by term
    summary = []
    for trend in items:
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

    return {"items": summary}


@router.get("/topics", response_model=TrendTopicListResponse)
def trends_topics(limit: int = 10):
    settings = load_trends_settings()
    articles = list_recent_articles(settings.db_path, limit=500)
    topics = build_topics(articles, max_topics=limit)
    return {"items": topics}



@router.get("/debug")
def trends_debug():
    settings = load_trends_settings()
    items = list_recent_articles(settings.db_path, limit=5)
    return {
        "sources": list_sources(settings.db_path, enabled_only=False),
        "recent_articles_count": len(list_recent_articles(settings.db_path, limit=500)),
        "recent_samples": items,
        "trends": list_trends(settings.db_path, limit=10),
    }

@router.get("/top", response_model=TrendListResponse)
def trends_top(limit: int = 50):
    settings = load_trends_settings()
    items = list_trends(settings.db_path, limit=limit)
    return TrendListResponse(items=items)


@router.get("/articles", response_model=TrendArticleListResponse)
def trends_articles(limit: int = 50):
    settings = load_trends_settings()
    items = list_recent_articles(settings.db_path, limit=limit)
    return TrendArticleListResponse(items=items)
