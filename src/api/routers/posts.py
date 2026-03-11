from fastapi import APIRouter, Depends, HTTPException, Query

from dependencies import get_post_analyzer
from schemas import TelegramPostResponse
from services.errors import (
    AuthorizationRequiredError,
    InvalidTelegramPostUrlError,
    TelegramOperationError,
    TelegramPostNotFoundError,
)
from services.interfaces import PostAnalyzerPort

router = APIRouter(prefix="/tg", tags=["telegram-posts"])


@router.get("/post", response_model=TelegramPostResponse)
async def tg_post(
    url: str = Query(...),
    post_analyzer: PostAnalyzerPort = Depends(get_post_analyzer),
):
    try:
        post = await post_analyzer.analyze(url)
    except AuthorizationRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except InvalidTelegramPostUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TelegramPostNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TelegramOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return TelegramPostResponse(
        url=post.url,
        channel=post.channel,
        message_id=post.message_id,
        text=post.text,
        date_iso=post.date_iso,
        views=post.views,
        forwards=post.forwards,
    )
