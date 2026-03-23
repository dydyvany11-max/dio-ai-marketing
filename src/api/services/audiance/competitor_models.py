from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompetitorMatchEvaluation:
    theme_similarity: float
    keyword_similarity: float
    interest_similarity: float
    audience_similarity: float
    engagement_similarity: float
    format_similarity: float
    dominant_theme_bonus: float
    niche_overlap: float
    dominant_specific_theme: str | None
    candidate_dominant_specific_theme: str | None
    matched_themes: list[str]
    matched_specific_themes: list[str]
    matched_generic_themes: list[str]
    matched_keywords: list[str]
    shared_theme_count: int
    shared_specific_theme_count: int
    generic_overlap_count: int
    disqualifiers: list[str]
    similarity_score: float
    relation_type: str
