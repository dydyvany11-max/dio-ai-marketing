from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.api.services.langgraph_smm import run_audience_graph

router = APIRouter()


class AudienceAnalyzeIn(BaseModel):
    platform: str = Field(..., description="vk or telegram")
    source_id: str = Field(..., description="Group/channel ID or URL")


@router.post("/audience/analyze")
def analyze_audience(payload: AudienceAnalyzeIn):
    return run_audience_graph(platform=payload.platform, source_id=payload.source_id)

