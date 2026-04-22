import psycopg
import pgvector.psycopg
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class SearchResult:
    id: str
    content: str
    file_path: str
    score: float          # distância coseno (0 = idêntico, 2 = oposto)
    metadata: dict


@dataclass
class FileBlock:
    id: str
    content: str
    file_path: str
    metadata: dict        # sem o campo embedding


@dataclass
class IndexedFile:
    file_path: str
    block_count: int
    language: str


class MCP_VectorStore:
    def __init__(self, settings) -> None:
        self._settings = settings

    def get_connection(self) -> psycopg.Connection:
        """Abre conexão psycopg v3 e registra o adaptador pgvector."""
        conn = psycopg.connect(
            host=self._settings.db_host,
            port=self._settings.db_port,
            dbname=self._settings.db_name,
            user=self._settings.db_user,
            password=self._settings.db_password,
        )
        pgvector.psycopg.register_vector(conn)
        return conn

    def cosine_search(
        self,
        conn: psycopg.Connection,
        query_vector: List[float],
        limit: int,
        language: Optional[str] = None,
        node_type: Optional[str] = None,
    ) -> List[SearchResult]:
        """Busca por similaridade coseno usando operador <=> do pgvector.
        Aplica filtros opcionais de language e node_type via metadata JSONB.
        Retorna lista vazia se nenhum resultado encontrado."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text, content, file_path, metadata,
                       embedding <=> %s::vector AS score
                FROM code_embeddings
                WHERE (%s::text IS NULL OR metadata->>'language' = %s::text)
                  AND (%s::text IS NULL OR metadata->>'node_type' = %s::text)
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_vector, language, language, node_type, node_type, query_vector, limit),
            )
            rows = cur.fetchall()

        return [
            SearchResult(
                id=row[0],
                content=row[1],
                file_path=row[2],
                metadata=row[3],
                score=float(row[4]),
            )
            for row in rows
        ]

    def get_file_blocks(
        self,
        conn: psycopg.Connection,
        file_path: str,
    ) -> List[FileBlock]:
        """Retorna todos os blocos de um arquivo ordenados por metadata->>'start_line' ASC.
        Retorna lista vazia se file_path não encontrado."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text, content, file_path, metadata
                FROM code_embeddings
                WHERE file_path = %s
                ORDER BY (metadata->>'start_line')::int ASC
                """,
                (file_path,),
            )
            rows = cur.fetchall()

        return [
            FileBlock(
                id=row[0],
                content=row[1],
                file_path=row[2],
                metadata=row[3],
            )
            for row in rows
        ]

    def list_indexed_files(
        self,
        conn: psycopg.Connection,
    ) -> List[IndexedFile]:
        """Retorna file_paths únicos com block_count e language, ordenados alfabeticamente."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT file_path, COUNT(*) AS block_count, MIN(metadata->>'language') AS language
                FROM code_embeddings
                GROUP BY file_path
                ORDER BY file_path ASC
                """
            )
            rows = cur.fetchall()

        return [
            IndexedFile(
                file_path=row[0],
                block_count=int(row[1]),
                language=row[2] or "",
            )
            for row in rows
        ]
