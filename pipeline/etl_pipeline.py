"""
ETL_Pipeline — orquestrador principal do pipeline de ingestão.

Requirements: 1.1, 1.2, 1.3, 1.4, 2.3, 2.4, 3.8, 3.9, 8.2, 8.3
"""
import asyncio
import time
from pathlib import Path
from typing import Dict, Any, List

from pipeline.grammar_router import Grammar_Router, SUPPORTED_EXTENSIONS
from pipeline.parser import Parser
from pipeline.deduplicator import Deduplicator
from pipeline.embedding_client import Embedding_Client
from pipeline.vector_store import Vector_Store
from utils.logging import get_logger

logger = get_logger(__name__)


class ETL_Pipeline:
    """Orquestra o pipeline completo: descoberta → deduplicação → parsing → embedding → persistência.

    Requirements: 1.1
    """

    def __init__(self, settings, job_store: Dict[str, Any]) -> None:
        self._settings = settings
        self._job_store = job_store
        self._grammar_router = Grammar_Router()
        self._parser = Parser()
        self._deduplicator = Deduplicator()
        self._embedding_client = Embedding_Client(
            api_key=settings.openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
            deployment_name=settings.azure_openai_deployment,
        )
        self._vector_store = Vector_Store(settings)

    def _discover_files(self, root: Path) -> List[Path]:
        """Percorre root recursivamente e retorna arquivos com extensões suportadas.

        Registra WARNING para arquivos sem permissão de leitura.

        Requirements: 1.1, 1.4
        """
        supported = set(SUPPORTED_EXTENSIONS)
        files = []
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in supported:
                try:
                    path.stat()  # check read permission
                    files.append(path)
                except PermissionError:
                    logger.warning(
                        "Permission denied",
                        extra={"file_path": str(path)},
                    )
        return files

    async def run(self, job_id: str, repository_path: str) -> None:
        """Orquestra o pipeline completo para um job.

        Atualiza job_store[job_id] com status e métricas em tempo real.

        Requirements: 1.1, 1.2, 1.3, 1.4, 2.3, 2.4, 3.8, 3.9, 8.2, 8.3
        """
        start_time = time.time()
        job = self._job_store[job_id]
        job["status"] = "running"

        root = Path(repository_path)
        if not root.exists():
            job["status"] = "failed"
            logger.error(
                "Repository path not found",
                extra={"path": repository_path},
            )
            return

        files = self._discover_files(root)
        job["metrics"]["files_discovered"] = len(files)

        conn = self._vector_store.get_connection()
        try:
            for file_path in files:
                await self._process_file(job, conn, file_path)
        finally:
            conn.close()

        elapsed = time.time() - start_time
        job["metrics"]["elapsed_seconds"] = elapsed
        job["status"] = "completed"
        logger.info(
            "Job completed",
            extra={"job_id": job_id, **job["metrics"]},
        )

    async def _process_file(self, job: Dict[str, Any], conn, file_path: Path) -> None:
        """Processa um único arquivo: hash → dedup → parse → embed → insert.

        Erros por arquivo não interrompem o pipeline (fail-per-file).

        Requirements: 1.2, 1.3, 2.3, 2.4, 3.8, 3.9, 8.2
        """
        try:
            file_bytes = file_path.read_bytes()
            sha256 = self._deduplicator.compute_hash(file_bytes)

            if self._vector_store.hash_exists(conn, sha256):
                job["metrics"]["files_skipped"] += 1
                logger.info(
                    "File skipped (duplicate)",
                    extra={
                        "file_path": str(file_path),
                        "status": "skipped",
                        "blocks_extracted": 0,
                        "embeddings_generated": 0,
                    },
                )
                return

            ts_parser = self._grammar_router.get_parser(file_path.suffix.lower())
            if ts_parser is None:
                job["metrics"]["files_skipped"] += 1
                logger.warning(
                    "No parser available for extension",
                    extra={
                        "file_path": str(file_path),
                        "status": "skipped",
                        "blocks_extracted": 0,
                        "embeddings_generated": 0,
                    },
                )
                return

            content = file_bytes.decode("utf-8", errors="replace")
            blocks = self._parser.parse(content, file_path, ts_parser, self._settings.sql_dialect)

            if not blocks:
                job["metrics"]["files_skipped"] += 1
                logger.warning(
                    "No semantic blocks found",
                    extra={
                        "file_path": str(file_path),
                        "status": "skipped",
                        "blocks_extracted": 0,
                        "embeddings_generated": 0,
                    },
                )
                return

            texts = [b.content for b in blocks]
            embeddings = self._embedding_client.embed_batch(texts)
            self._vector_store.insert_batch(conn, blocks, embeddings, str(file_path), sha256)

            job["metrics"]["files_processed"] += 1
            job["metrics"]["blocks_inserted"] += len(blocks)
            logger.info(
                "File processed",
                extra={
                    "file_path": str(file_path),
                    "blocks_extracted": len(blocks),
                    "embeddings_generated": len(embeddings),
                    "status": "success",
                },
            )

        except PermissionError:
            job["metrics"]["files_failed"] += 1
            logger.warning(
                "Permission denied reading file",
                extra={
                    "file_path": str(file_path),
                    "status": "failed",
                    "blocks_extracted": 0,
                    "embeddings_generated": 0,
                },
            )
        except Exception as exc:
            job["metrics"]["files_failed"] += 1
            logger.error(
                "File processing failed",
                extra={
                    "file_path": str(file_path),
                    "error": str(exc),
                    "status": "failed",
                    "blocks_extracted": 0,
                    "embeddings_generated": 0,
                },
            )
