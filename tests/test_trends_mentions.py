from src.api.services.trends_mentions import analyze_mentions, build_query_terms


def test_build_query_terms_deduplicates_and_cleans():
    terms = build_query_terms("  Fast Food Music  ", ["FFM", "ffm", "", "  Fast Food Music "])
    assert terms == ["Fast Food Music", "FFM"]


def test_analyze_mentions_finds_company_and_aliases():
    articles = [
        {
            "source": "vk",
            "url": "https://example.com/1",
            "title": "Fast Food Music выпустили новый релиз",
            "content": "По данным редакции Fast Food Music, это лучший релиз месяца. FFM тоже в тренде.",
            "published_at": "2026-03-26T10:00:00Z",
        },
        {
            "source": "telegram",
            "url": "https://example.com/2",
            "title": "Новости кино",
            "content": "Про музыку тут ничего нет.",
            "published_at": "2026-03-26T11:00:00Z",
        },
    ]

    result = analyze_mentions(
        articles=articles,
        company="Fast Food Music",
        aliases=["FFM"],
        limit=10,
    )

    assert result["scanned_articles"] == 2
    assert result["matched_articles"] == 1
    assert result["total_mentions"] >= 3
    assert result["items"]
    first = result["items"][0]
    assert first["source"] == "vk"
    assert "Fast Food Music" in first["matched_terms"]
    assert "FFM" in first["matched_terms"]


def test_analyze_mentions_respects_limit():
    articles = []
    for idx in range(6):
        articles.append(
            {
                "source": "vk",
                "url": f"https://example.com/{idx}",
                "title": f"BrandX mention {idx}",
                "content": "BrandX снова в инфополе",
                "published_at": None,
            }
        )

    result = analyze_mentions(articles=articles, company="BrandX", aliases=[], limit=3)
    assert result["matched_articles"] == 6
    assert len(result["items"]) == 3
