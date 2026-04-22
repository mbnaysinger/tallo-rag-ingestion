import sys
import json
import logging
import time
from typing import Optional
from pathlib import Path

# Logging para stderr — stdout reservado ao protocolo MCP
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger(__name__)

# Garante que a raiz do repositório está no sys.path
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastmcp import FastMCP

from tallo_mcp.config import load_mcp_settings
from tallo_mcp.db import MCP_VectorStore
from pipeline.embedding_client import Embedding_Client

settings = load_mcp_settings()
_vector_store = MCP_VectorStore(settings)
_embedding_client = Embedding_Client(
    api_key=settings.openai_api_key,
    azure_endpoint=settings.azure_openai_endpoint,
    api_version=settings.azure_openai_api_version,
    deployment_name=settings.azure_openai_deployment,
)

mcp = FastMCP("tallo-rag", version="1.0.0")


def _log(tool_name: str, params: dict, execution_ms: float, extra: dict = None):
    """Emite uma linha JSON para stderr com metadados de invocação da tool."""
    record = {
        "tool_name": tool_name,
        "params": params,
        "execution_ms": round(execution_ms, 3),
    }
    if extra:
        record.update(extra)
    logger.info(json.dumps(record))


@mcp.tool()
def search_code(
    query: str,
    limit: int = 10,
    language: Optional[str] = None,
    node_type: Optional[str] = None,
    expand_dependencies: bool = False,
    dependency_depth: int = 1,
) -> list:
    """Busca blocos de código semanticamente similares à query fornecida.

    Se expand_dependencies=True, expande automaticamente as dependências dos
    resultados (Java: @Inject/extends/implements; CFML: cfinvoke/new) até
    dependency_depth níveis, retornando o contexto completo da cadeia de chamadas.
    """
    if not query:
        raise ValueError("query cannot be empty")
    if limit < 1 or limit > 50:
        raise ValueError(f"limit must be between 1 and 50, got: {limit}")
    if dependency_depth < 1 or dependency_depth > 3:
        raise ValueError(f"dependency_depth must be between 1 and 3, got: {dependency_depth}")

    t0 = time.monotonic()
    vectors = _embedding_client.embed_batch([query])
    query_vector = vectors[0]

    with _vector_store.get_connection() as conn:
        results = _vector_store.cosine_search(
            conn, query_vector, limit, language=language, node_type=node_type
        )

        dependencies: list = []
        if expand_dependencies and results:
            dep_blocks = _vector_store.expand_dependencies(conn, results, depth=dependency_depth)
            dependencies = [
                {
                    "id": b.id,
                    "content": b.content,
                    "file_path": b.file_path,
                    "score": None,
                    "metadata": b.metadata,
                    "_dependency": True,
                }
                for b in dep_blocks
            ]

    execution_ms = (time.monotonic() - t0) * 1000
    _log(
        "search_code",
        {
            "query": query,
            "limit": limit,
            "language": language,
            "node_type": node_type,
            "expand_dependencies": expand_dependencies,
            "dependency_depth": dependency_depth,
        },
        execution_ms,
        {"result_count": len(results), "dependency_count": len(dependencies)},
    )

    primary = [
        {
            "id": r.id,
            "content": r.content,
            "file_path": r.file_path,
            "score": r.score,
            "metadata": r.metadata,
        }
        for r in results
    ]

    return primary + dependencies


@mcp.tool()
def get_file_blocks(file_path: str) -> list:
    """Retorna todos os blocos indexados de um arquivo específico."""
    if not file_path:
        raise ValueError("file_path cannot be empty")

    t0 = time.monotonic()
    with _vector_store.get_connection() as conn:
        blocks = _vector_store.get_file_blocks(conn, file_path)

    execution_ms = (time.monotonic() - t0) * 1000
    _log(
        "get_file_blocks",
        {"file_path": file_path},
        execution_ms,
        {"result_count": len(blocks)},
    )

    return [
        {
            "id": b.id,
            "content": b.content,
            "file_path": b.file_path,
            "metadata": b.metadata,
        }
        for b in blocks
    ]


@mcp.tool()
def list_indexed_files() -> list:
    """Lista todos os arquivos únicos indexados no banco vetorial."""
    t0 = time.monotonic()
    with _vector_store.get_connection() as conn:
        files = _vector_store.list_indexed_files(conn)

    execution_ms = (time.monotonic() - t0) * 1000
    _log(
        "list_indexed_files",
        {},
        execution_ms,
        {"result_count": len(files)},
    )

    return [
        {
            "file_path": f.file_path,
            "block_count": f.block_count,
            "language": f.language,
        }
        for f in files
    ]


if __name__ == "__main__":
    mcp.run(transport="stdio")
