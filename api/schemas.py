from pydantic import BaseModel
from typing import Optional, Literal


class IngestRequest(BaseModel):
    repository_path: str


class IngestResponse(BaseModel):
    job_id: str
    status: Literal["pending"] = "pending"


class JobMetrics(BaseModel):
    files_discovered: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    blocks_inserted: int = 0
    elapsed_seconds: Optional[float] = None


class StatusResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed"]
    metrics: JobMetrics
