import hashlib


class Deduplicator:
    def compute_hash(self, file_bytes: bytes) -> str:
        """Retorna hex digest SHA-256 do conteúdo binário do arquivo."""
        return hashlib.sha256(file_bytes).hexdigest()
