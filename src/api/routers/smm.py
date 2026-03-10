from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.api.services.langgraph_smm import run_audience_graph

router = APIRouter()


class AudienceAnalyzeIn(BaseModel):
    platform: str = Field(..., description="vk или telegram")
    source_id: str = Field(..., description="ID группы/канала или ссылка на него")


@router.post("/audience/analyze")
def analyze_audience(payload: AudienceAnalyzeIn):
    return run_audience_graph(platform=payload.platform, source_id=payload.source_id)
