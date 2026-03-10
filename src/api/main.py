from fastapi import FastAPI
from src.api.routers import smm


app = FastAPI(title="DIO AI Marketing API")
app.include_router(smm.router, prefix="/smm", tags=["smm"])


def run() -> None:
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    run()
