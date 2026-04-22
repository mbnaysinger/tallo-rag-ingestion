"""
Entrypoint FastAPI — app, lifespan e inclusão do router.

Requirements: 6.1
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes import router
from config import load_settings
from pipeline.etl_pipeline import ETL_Pipeline
from pipeline.vector_store import Vector_Store


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    job_store: dict = {}
    app.state.settings = settings
    app.state.job_store = job_store
    app.state.etl_pipeline = ETL_Pipeline(settings, job_store)
    app.state.vector_store = Vector_Store(settings)
    yield


app = FastAPI(title="Tallo RAG Ingestion Service", lifespan=lifespan)
app.include_router(router)
