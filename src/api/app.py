from fastapi import FastAPI

from dependencies import get_client_service
from routers.auth import router as auth_router
from routers.posts import router as posts_router
from routers.system import router as system_router


def create_app() -> FastAPI:
    app = FastAPI(title="Telegram QR Auth + Post Analyzer")
    client_service = get_client_service()

    @app.on_event("startup")
    async def startup() -> None:
        await client_service.ensure_connected()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await client_service.disconnect()

    app.include_router(system_router)
    app.include_router(auth_router)
    app.include_router(posts_router)
    return app


app = create_app()
