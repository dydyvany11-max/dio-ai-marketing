import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import feedparser

try:
    import trafilatura
    import trafilatura.extract
except Exception:
    trafilatura = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

from src.api.services.trends_db import Article


@dataclass
class Source:
    id: int
    name: str
    url: str
    type: str
    meta_json: str | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_newsapi(api_key: str, sources: list[str], page_size: int = 50) -> list[Article]:
    if not api_key or not sources:
        return []
    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "sources": ",".join(sources),
        "pageSize": page_size,
        "apiKey": api_key,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    articles: list[Article] = []
    for item in data.get("articles", []):
        articles.append(
            Article(
                source_id=None,
                source=item.get("source", {}).get("name") or "newsapi",
                url=item.get("url") or "",
                title=item.get("title") or "",
                content=(item.get("description") or "") + " " + (item.get("content") or ""),
                published_at=item.get("publishedAt"),
                fetched_at=_utc_now(),
            )
        )
    return [a for a in articles if a.url]


def _fetch_gdelt(query: str, maxrecords: int = 50) -> list[Article]:
    if not query:
        return []
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": maxrecords,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    articles: list[Article] = []
    for item in data.get("articles", []):
        articles.append(
            Article(
                source_id=None,
                source=item.get("sourcecountry") or "gdelt",
                url=item.get("url") or "",
                title=item.get("title") or "",
                content=item.get("seendate") or "",
                published_at=item.get("seendate"),
                fetched_at=_utc_now(),
            )
        )
    return [a for a in articles if a.url]


def _render_page_html(url: str, wait_ms: int = 3000) -> str:
    if sync_playwright is None:
        return ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        try:
            page.wait_for_selector("article", timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(wait_ms)

        html = page.content()
        browser.close()
    return html or ""


def _render_fallback_text(url: str, wait_ms: int = 3000) -> str:
    if sync_playwright is None:
        return ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        try:
            page.wait_for_selector("article", timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(wait_ms)
        js = """
        () => {
          const bad = (t) => /privacy|cookie|consent|preferences|subscribe|sign in/i.test(t);
          const pick = () => {
            const article = document.querySelector('article');
            if (article) return article.innerText || '';
            const main = document.querySelector('main');
            if (main) return main.innerText || '';
            return document.body ? document.body.innerText : '';
          };
          let text = pick();
          let lines = text.split('\n').map(l => l.trim()).filter(Boolean);
          lines = lines.filter(l => !bad(l));
          if (lines.length < 20) {
            const heads = Array.from(document.querySelectorAll('h1,h2,h3'))
              .map(h => (h.innerText || '').trim())
              .filter(t => t && !bad(t));
            lines = heads;
          }
          return lines.join('
');
        }
        """
        text = page.evaluate(js)
        browser.close()
    return text or ""


def _extract_readable(url: str, html: str) -> tuple[str, str]:
    if not html:
        return "", ""
    if trafilatura is None:
        return "", ""
    text = trafilatura.extract(html, url=url, include_links=False, include_formatting=False) or ""
    title = ""
    try:
        meta = trafilatura.extract_metadata(html, url=url)
        if meta and meta.title:
            title = meta.title
    except Exception:
        title = ""
    return title.strip(), text.strip()


def _fetch_rss(source: Source, max_items: int = 50) -> list[Article]:
    feed = feedparser.parse(source.url)
    articles: list[Article] = []
    for entry in feed.entries[:max_items]:
        title = entry.get("title") or ""
        link = entry.get("link") or ""
        published = entry.get("published") or entry.get("updated")
        summary = entry.get("summary") or ""
        articles.append(
            Article(
                source_id=source.id,
                source=source.name,
                url=link,
                title=title,
                content=summary,
                published_at=published,
                fetched_at=_utc_now(),
            )
        )
    return [a for a in articles if a.url]


def _extract_links_from_page(source: Source, html: str, max_links: int = 15) -> list[str]:
    if not html:
        return []
    if trafilatura is None:
        return []
    try:
        # Use trafilatura to find links in the page
        links = trafilatura.extract_links(html, url=source.url) or []
    except Exception:
        links = []

    base = urlparse(source.url).netloc
    cleaned = []
    for link in links:
        if not link or not isinstance(link, str):
            continue
        full = urljoin(source.url, link)
        if urlparse(full).netloc != base:
            continue
        if any(x in full for x in ["/privacy", "/cookie", "/consent", "/login", "/signin"]):
            continue
        cleaned.append(full.split("#")[0])

    # de-dup
    uniq = list(dict.fromkeys(cleaned))
    return uniq[:max_links]


def _fetch_html_articles(source: Source) -> list[Article]:
    html = _render_page_html(source.url)
    title, content = _extract_readable(source.url, html)

    # If this looks like a list page, try multiple links
    meta = {}
    if source.meta_json:
        try:
            meta = json.loads(source.meta_json)
        except Exception:
            meta = {}
    max_links = int(meta.get("max_links", 12)) if isinstance(meta, dict) else 12

    links = _extract_links_from_page(source, html, max_links=max_links)
    articles: list[Article] = []

    if links:
        for link in links:
            try:
                resp = requests.get(link, timeout=20)
                page_html = resp.text
                atitle, acontent = _extract_readable(link, page_html)
                if not acontent:
                    continue
                if not atitle:
                    atitle = link
                articles.append(
                    Article(
                        source_id=source.id,
                        source=source.name,
                        url=link,
                        title=atitle,
                        content=acontent,
                        published_at=None,
                        fetched_at=_utc_now(),
                    )
                )
            except Exception:
                continue

    if not articles and content:
        if not title:
            lines = [l.strip() for l in content.split("\n") if l.strip()]
            title = lines[0][:200] if lines else source.name
        articles.append(
            Article(
                source_id=source.id,
                source=source.name,
                url=source.url,
                title=title,
                content=content,
                published_at=None,
                fetched_at=_utc_now(),
            )
        )

    return articles


def collect_from_sources(
    sources: list[Source],
    newsapi_key: str | None = None,
    newsapi_sources: list[str] | None = None,
    gdelt_query: str | None = None,
) -> list[Article]:
    articles: list[Article] = []

    if newsapi_key and newsapi_sources:
        try:
            articles.extend(_fetch_newsapi(newsapi_key, newsapi_sources))
        except Exception:
            pass

    if gdelt_query:
        try:
            articles.extend(_fetch_gdelt(gdelt_query))
        except Exception:
            pass

    for src in sources:
        if src.type == "html":
            try:
                articles.extend(_fetch_html_articles(src))
            except Exception:
                continue
        elif src.type == "rss":
            try:
                articles.extend(_fetch_rss(src))
            except Exception:
                continue

    return articles


def parse_sources(rows: list[dict]) -> list[Source]:
    sources: list[Source] = []
    for row in rows:
        sources.append(
            Source(
                id=int(row["id"]),
                name=row["name"],
                url=row["url"],
                type=row["type"],
                meta_json=row.get("meta_json"),
            )
        )
    return sources
