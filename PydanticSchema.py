import datetime
class ShemaPost:
    platform: str
    source_id: str
    external_post_id: str
    text: str
    published_at: datetime
    views: int | None
    likes: int | None
    comments_count: int | None
    reposts_count: int | None
    url: str