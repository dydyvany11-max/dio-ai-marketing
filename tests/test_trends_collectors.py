from src.api.services.trends_collectors import parse_sources


def test_parse_sources_normalizes_type_from_db_values():
    rows = [
        {"id": 1, "name": "A", "url": "https://example.com/feed.xml", "type": "RSS", "meta_json": None},
        {"id": 2, "name": "B", "url": "https://example.com/news", "type": "News", "meta_json": None},
        {"id": 3, "name": "C", "url": "https://example.com/site", "type": "unknown", "meta_json": None},
    ]
    parsed = parse_sources(rows)
    assert parsed[0].type == "rss"
    assert parsed[1].type == "html"
    assert parsed[2].type == "html"
