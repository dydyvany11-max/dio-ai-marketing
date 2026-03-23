from __future__ import annotations

from pydantic import BaseModel, Field


class AITheme(BaseModel):
    key: str
    label: str
    share: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class AIPersona(BaseModel):
    title: str
    description: str
    age_range: str
    persona_summary: str
    motivations: list[str]
    content_preferences: list[str]
    activity_pattern: str


class AIAudienceInsights(BaseModel):
    dominant_theme: AITheme
    channel_themes: list[AITheme]
    audience_persona: AIPersona
    summary: str


class KeywordItem(BaseModel):
    index: int
    keywords: list[str] = Field(default_factory=list)


class KeywordBatchResult(BaseModel):
    items: list[KeywordItem] = Field(default_factory=list)
