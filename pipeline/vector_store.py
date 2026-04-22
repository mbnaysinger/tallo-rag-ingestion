import json
import psycopg
import pgvector.psycopg
from typing import List

from models.code_block import Code_Block


class Vector_Store:
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

    def hash_exists(self, conn: psycopg.Connection, sha256_hex: str) -> bool:
        """Retorna True se já existe um registro com o hash SHA-256 fornecido."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM code_embeddings WHERE metadata->>'file_sha256' = %s LIMIT 1",
                (sha256_hex,),
            )
            return cur.fetchone() is not None

    def insert_batch(
        self,
        conn: psycopg.Connection,
        blocks: List[Code_Block],
        embeddings: List[List[float]],
        file_path: str,
        sha256_hex: str,
    ) -> None:
        """Insere todos os registros de um arquivo em uma única transação.
        Em caso de falha, realiza rollback e propaga a exceção."""
        try:
            with conn.cursor() as cur:
                for block, embedding in zip(blocks, embeddings):
                    metadata = {
                        "node_type": block.node_type,
                        "language": block.language,
                        "start_line": block.start_line,
                        "end_line": block.end_line,
                        "file_sha256": sha256_hex,
                        **block.metadata,
                    }
                    cur.execute(
                        "INSERT INTO code_embeddings (content, file_path, metadata, embedding)"
                        " VALUES (%s, %s, %s, %s)",
                        (block.content, file_path, json.dumps(metadata), embedding),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
