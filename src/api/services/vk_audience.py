from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from src.api.services.dto import (
    VKAudienceReport,
    VKGroupInfo,
    VKPostMetrics,
)
from src.api.services.errors import VKOperationError
from src.api.services.vk_client import VKClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VKGroupResolved:
    group_id: int
    name: str
    screen_name: str | None
    members_count: int | None


class VKAudienceAnalyzer:
    def __init__(self, vk_client: VKClient):
        self._vk = vk_client

    def analyze(self, source: str, access_token: str, post_limit: int = 50) -> VKAudienceReport:
        if not source:
            raise VKOperationError("source is required")

        group = self._resolve_group(source, access_token)
        posts = self._get_wall_posts(group.group_id, access_token, post_limit)
        metrics = [self._to_metrics(post) for post in posts]

        limitations = []
        if not metrics:
            limitations.append("Нет постов для анализа или доступ к стене ограничен.")

        avg_views = self._avg(metric.views for metric in metrics)
        avg_likes = self._avg(metric.likes for metric in metrics)
        avg_comments = self._avg(metric.comments for metric in metrics)
        avg_reposts = self._avg(metric.reposts for metric in metrics)
        posts_per_day = self._posts_per_day(metrics)

        top_posts = sorted(metrics, key=lambda item: item.views, reverse=True)[:3]

        return VKAudienceReport(
            group=VKGroupInfo(
                group_id=group.group_id,
                name=group.name,
                screen_name=group.screen_name,
                members_count=group.members_count,
            ),
            average_views=avg_views,
            average_likes=avg_likes,
            average_comments=avg_comments,
            average_reposts=avg_reposts,
            posts_per_day=posts_per_day,
            total_posts_analyzed=len(metrics),
            top_posts=top_posts,
            limitations=limitations,
        )

    def _resolve_group(self, source: str, access_token: str) -> VKGroupResolved:
        normalized = self._normalize_source(source)
        params = {"group_id": normalized, "fields": "members_count,screen_name,name"}
        response = self._vk.call_api("groups.getById", access_token, **params)
        if not response:
            raise VKOperationError("VK group not found")
        group = response[0]
        return VKGroupResolved(
            group_id=int(group.get("id")),
            name=group.get("name", ""),
            screen_name=group.get("screen_name"),
            members_count=group.get("members_count"),
        )

    def _get_wall_posts(self, group_id: int, access_token: str, limit: int) -> list[dict]:
        owner_id = -abs(group_id)
        limit = max(1, min(limit, 100))
        response = self._vk.call_api(
            "wall.get",
            access_token,
            owner_id=owner_id,
            count=limit,
            filter="owner",
            extended=0,
        )
        items = response.get("items", []) if isinstance(response, dict) else []
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _normalize_source(source: str) -> str:
        value = source.strip()
        if value.startswith("https://") or value.startswith("http://"):
            value = value.split("vk.com/")[-1].strip("/")
        if value.startswith("public"):
            value = value.replace("public", "")
        if value.startswith("club"):
            value = value.replace("club", "")
        if value.startswith("@"):
            value = value[1:]
        return value

    @staticmethod
    def _to_metrics(item: dict) -> VKPostMetrics:
        views = 0
        if isinstance(item.get("views"), dict):
            views = int(item["views"].get("count", 0) or 0)
        likes = int(item.get("likes", {}).get("count", 0) or 0)
        comments = int(item.get("comments", {}).get("count", 0) or 0)
        reposts = int(item.get("reposts", {}).get("count", 0) or 0)
        return VKPostMetrics(
            post_id=int(item.get("id", 0) or 0),
            date=int(item.get("date", 0) or 0),
            views=views,
            likes=likes,
            comments=comments,
            reposts=reposts,
        )

    @staticmethod
    def _avg(values: Iterable[int]) -> int:
        items = list(values)
        if not items:
            return 0
        return int(sum(items) / len(items))

    @staticmethod
    def _posts_per_day(metrics: list[VKPostMetrics]) -> float:
        if len(metrics) < 2:
            return 0.0
        dates = sorted(metric.date for metric in metrics if metric.date)
        if len(dates) < 2:
            return 0.0
        span_days = max((datetime.fromtimestamp(dates[-1]) - datetime.fromtimestamp(dates[0])).total_seconds() / 86400, 1 / 24)
        return round(len(dates) / span_days, 3)
