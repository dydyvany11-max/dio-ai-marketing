from fastapi import APIRouter

from src.api.config import is_gigachat_configured, load_gigachat_settings, load_trends_settings
from src.api.schemas import TrendRefreshResponse, TrendSourceListResponse
from src.api.services.trends_ai import GigaChatTrendsLabeler
from src.api.services.trends_collectors import collect_from_sources, parse_sources
from src.api.services.trends_db import (
    init_db,
    list_recent_articles,
    list_sources,
    list_trends,
    save_trends,
    store_articles,
)
from src.api.services.trends_engine import compute_trends, quick_trends_from_articles, update_term_counts

router = APIRouter(prefix="/trends", tags=["Trends"])


@router.get("/sources", response_model=TrendSourceListResponse, summary="Configured Trend Sources")
def trends_sources():
    settings = load_trends_settings()
    rows = list_sources(settings.db_path, enabled_only=False)
    return TrendSourceListResponse(items=rows)


@router.post("/refresh", response_model=TrendRefreshResponse, summary="Refresh Trends From Enabled Sources")
def trends_refresh():
    settings = load_trends_settings()
    init_db(settings.db_path)
    sources = parse_sources(list_sources(settings.db_path, enabled_only=True))

    inserted = 0
    if sources:
        articles = collect_from_sources(
            sources,
            newsapi_key=settings.newsapi_key,
            newsapi_sources=settings.newsapi_sources,
            gdelt_query=settings.gdelt_query,
            rss_max_items=60,
            html_max_links=6,
            crawl_html_links=False,
            timeout_sec=10,
            use_playwright_html=True,
            playwright_max_items=35,
        )
        inserted = store_articles(settings.db_path, articles)

    recent = list_recent_articles(settings.db_path, limit=700)
    update_term_counts(settings.db_path, recent)
    trends = compute_trends(settings.db_path, window_hours=settings.window_hours, max_terms=settings.max_terms)
    if not trends:
        trends = quick_trends_from_articles(recent, max_terms=settings.max_terms)
        if trends:
            save_trends(settings.db_path, trends)

    return TrendRefreshResponse(inserted=inserted, trends=trends)


@router.get("/report", summary="Trend Report")
def trends_report(
    limit: int = 10,
    company: str | None = None,
):
    settings = load_trends_settings()
    trends = list_trends(settings.db_path, limit=limit)
    articles = list_recent_articles(settings.db_path, limit=700)
    ai = {"enabled": False, "available": False, "message": "GigaChat is not configured"}
    ai_analysis: dict = {
        "summary": "",
        "key_trends": [],
        "infopovody": [],
        "potential_risks": [],
        "company_mentions": [],
        "limitations": [],
    }
    if is_gigachat_configured() and articles:
        try:
            labeler = GigaChatTrendsLabeler(load_gigachat_settings())
            ai_analysis = labeler.analyze_landscape(
                articles=articles,
                trends=trends,
                company=(company or "").strip() or None,
                language="ru",
            )
            ai = {"enabled": True, "available": True, "message": "GigaChat trend analysis completed"}
        except Exception as exc:
            ai = {"enabled": True, "available": False, "message": f"GigaChat error: {exc}"}
            ai_analysis["limitations"] = [f"GigaChat error: {exc}"]

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
        if not titles:
            for art in articles:
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
        "ai": ai,
        "ai_analysis": ai_analysis,
    }
