import logging
import os

from fastapi import FastAPI

from src.api.app_setup import configure_lifecycle, configure_routes
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="DIO AI Marketing API")
    configure_routes(app)
    configure_lifecycle(app)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=os.getenv("API_RELOAD", "false").lower() == "true",
    )


if __name__ == "__main__":
    run()
