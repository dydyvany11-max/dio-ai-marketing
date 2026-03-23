from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MessageStats:
    text: str
    date: datetime
    views: int
    forwards: int
    replies: int
    reactions: int


@dataclass(frozen=True)
class PostTopicProfile:
    tokens: list[str]
    token_counts: Counter[str]
    category_scores: Counter[str]
    evidence_map: dict[str, Counter[str]]
