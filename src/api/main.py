from fastapi import FastAPI
from src.api.routers import smm


app = FastAPI(title="DIO AI Marketing API")
app.include_router(smm.router, prefix="/smm", tags=["smm"])

