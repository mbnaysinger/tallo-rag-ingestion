"""
Testes de propriedade para a camada de API.

Property 19: POST /ingest retorna 202 com job_id único
Property 20: Status do job tem valores válidos e métricas não-negativas

Requirements: 7.1, 7.2, 7.3
"""
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from hypothesis import given, settings
from hypothesis import strategies as st

from api.routes import router


# ---------------------------------------------------------------------------
# Helpers — build a minimal test app with pre-populated state (no lifespan)
# ---------------------------------------------------------------------------

def _make_test_app(job_store: "dict | None" = None) -> FastAPI:
    """Create a FastAPI test app with mocked state set directly (no lifespan)."""
    if job_store is None:
        job_store = {}

    mock_settings = MagicMock()
    mock_settings.openai_api_key = "test-key"

    mock_etl = MagicMock()
    mock_etl.run = AsyncMock(return_value=None)

    mock_conn = MagicMock()
    mock_vector_store = MagicMock()
    mock_vector_store.get_connection.return_value = mock_conn

    test_app = FastAPI()
    test_app.include_router(router)

    # Set state directly — no lifespan needed for tests
    test_app.state.settings = mock_settings
    test_app.state.job_store = job_store
    test_app.state.etl_pipeline = mock_etl
    test_app.state.vector_store = mock_vector_store

    return test_app


# ---------------------------------------------------------------------------
# Property 19: POST /ingest retorna 202 com job_id único
# Validates: Requirements 7.1, 7.2
# ---------------------------------------------------------------------------

@settings(max_examples=50)
@given(paths=st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=10))
def test_property_19_post_ingest_returns_202_with_unique_uuid(paths):
    """
    **Validates: Requirements 7.1, 7.2**

    Property 19: POST /ingest retorna 202 com job_id único.
    Para qualquer repository_path string não-vazia, POST /ingest deve retornar
    HTTP 202 com um job_id no formato UUID que seja único entre todas as requisições.
    """
    job_store: dict = {}
    test_app = _make_test_app(job_store)

    async def run():
        job_ids = []
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            for path in paths:
                response = await client.post("/ingest", json={"repository_path": path})
                assert response.status_code == 202, (
                    f"Expected 202, got {response.status_code} for path={path!r}"
                )
                data = response.json()
                assert "job_id" in data, "Response must contain job_id"
                job_id = data["job_id"]
                # Must be a valid UUID
                parsed = uuid.UUID(job_id)
                assert str(parsed) == job_id, f"job_id {job_id!r} is not a canonical UUID"
                # Must be unique
                assert job_id not in job_ids, f"Duplicate job_id detected: {job_id}"
                job_ids.append(job_id)

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Property 20: Status do job tem valores válidos e métricas não-negativas
# Validates: Requirements 7.3
# ---------------------------------------------------------------------------

VALID_STATUSES = {"pending", "running", "completed", "failed"}


@st.composite
def job_state_strategy(draw):
    """Gera um estado de job válido para popular o job_store."""
    status = draw(st.sampled_from(list(VALID_STATUSES)))
    files_discovered = draw(st.integers(min_value=0, max_value=100))
    files_processed = draw(st.integers(min_value=0, max_value=100))
    files_skipped = draw(st.integers(min_value=0, max_value=100))
    files_failed = draw(st.integers(min_value=0, max_value=100))
    blocks_inserted = draw(st.integers(min_value=0, max_value=500))
    elapsed_seconds = draw(
        st.one_of(st.none(), st.floats(min_value=0.0, max_value=3600.0, allow_nan=False))
    )
    return {
        "status": status,
        "metrics": {
            "files_discovered": files_discovered,
            "files_processed": files_processed,
            "files_skipped": files_skipped,
            "files_failed": files_failed,
            "blocks_inserted": blocks_inserted,
            "elapsed_seconds": elapsed_seconds,
        },
    }


@settings(max_examples=50)
@given(job_state=job_state_strategy())
def test_property_20_status_has_valid_values_and_non_negative_metrics(job_state):
    """
    **Validates: Requirements 7.3**

    Property 20: Status do job tem valores válidos e métricas não-negativas.
    Para qualquer job criado via POST /ingest, GET /ingest/{job_id}/status deve
    retornar status em {"pending", "running", "completed", "failed"} e todos os
    campos numéricos de métricas devem ser >= 0.
    """
    job_id = str(uuid.uuid4())
    job_store = {job_id: job_state}
    test_app = _make_test_app(job_store)

    async def run():
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            response = await client.get(f"/ingest/{job_id}/status")
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}"
            )
            data = response.json()

            # status must be one of the valid values
            assert data["status"] in VALID_STATUSES, (
                f"Invalid status: {data['status']!r}"
            )

            # all numeric metrics must be >= 0
            metrics = data["metrics"]
            numeric_fields = [
                "files_discovered",
                "files_processed",
                "files_skipped",
                "files_failed",
                "blocks_inserted",
            ]
            for field in numeric_fields:
                assert metrics[field] >= 0, (
                    f"Metric {field} is negative: {metrics[field]}"
                )

            # elapsed_seconds, if present, must be >= 0
            if metrics.get("elapsed_seconds") is not None:
                assert metrics["elapsed_seconds"] >= 0, (
                    f"elapsed_seconds is negative: {metrics['elapsed_seconds']}"
                )

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Example tests — 404 for unknown job_id, 422 without repository_path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_status_404_for_unknown_job():
    """GET /ingest/{job_id}/status returns 404 for unknown job_id."""
    test_app = _make_test_app()
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(f"/ingest/{uuid.uuid4()}/status")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_post_ingest_422_without_repository_path():
    """POST /ingest returns 422 when repository_path is missing."""
    test_app = _make_test_app()
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/ingest", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_health_returns_200():
    """GET /health returns 200 with db and openai status."""
    test_app = _make_test_app()
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "db" in data
    assert "openai" in data
