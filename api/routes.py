"""
API routes — POST /ingest, GET /ingest/{job_id}/status, GET /health.

Requirements: 7.1, 7.2, 7.3, 7.5
"""
import asyncio
import uuid

from fastapi import APIRouter, HTTPException, Request

from api.schemas import IngestRequest, IngestResponse, JobMetrics, StatusResponse

router = APIRouter()


@router.post("/ingest", status_code=202)
async def start_ingest(request: Request, body: IngestRequest) -> IngestResponse:
    """Inicia ETL_Pipeline assíncrono e retorna job_id imediatamente.

    Requirements: 7.1, 7.2
    """
    job_id = str(uuid.uuid4())
    job_store = request.app.state.job_store
    etl_pipeline = request.app.state.etl_pipeline

    job_store[job_id] = {
        "status": "pending",
        "metrics": {
            "files_discovered": 0,
            "files_processed": 0,
            "files_skipped": 0,
            "files_failed": 0,
            "blocks_inserted": 0,
            "elapsed_seconds": None,
        },
    }

    asyncio.create_task(etl_pipeline.run(job_id, body.repository_path))
    return IngestResponse(job_id=job_id)


@router.get("/ingest/{job_id}/status")
async def get_status(job_id: str, request: Request) -> StatusResponse:
    """Retorna status e métricas do job.

    Requirements: 7.3
    """
    job_store = request.app.state.job_store
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = job_store[job_id]
    return StatusResponse(
        job_id=job_id,
        status=job["status"],
        metrics=JobMetrics(**job["metrics"]),
    )


@router.get("/health")
async def health_check(request: Request) -> dict:
    """Verifica conectividade com PostgreSQL e OpenAI.

    Requirements: 7.5
    """
    result: dict = {}

    # Check PostgreSQL connectivity
    try:
        vector_store = request.app.state.vector_store
        conn = vector_store.get_connection()
        conn.close()
        result["db"] = "healthy"
    except Exception as exc:
        result["db"] = f"unhealthy: {exc}"

    # Check OpenAI API key is configured
    try:
        settings = request.app.state.settings
        if settings.openai_api_key:
            result["openai"] = "healthy"
        else:
            result["openai"] = "unhealthy: OPENAI_API_KEY not set"
    except Exception as exc:
        result["openai"] = f"unhealthy: {exc}"

    return result
