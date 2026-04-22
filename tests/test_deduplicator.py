"""
Testes de propriedade para pipeline/deduplicator.py
"""
import pytest
from hypothesis import given, settings, strategies as st

from pipeline.deduplicator import Deduplicator


# Property 2: Idempotência do hash SHA-256
# Validates: Requirements 2.1
@settings(max_examples=100)
@given(st.binary())
def test_compute_hash_idempotent_and_64_chars(file_bytes: bytes):
    """
    **Validates: Requirements 2.1**

    Para qualquer sequência de bytes, compute_hash deve:
    - Retornar sempre o mesmo valor quando chamado múltiplas vezes com o mesmo input
    - Retornar uma string de exatamente 64 caracteres
    """
    dedup = Deduplicator()

    result1 = dedup.compute_hash(file_bytes)
    result2 = dedup.compute_hash(file_bytes)

    assert result1 == result2, "compute_hash deve ser idempotente"
    assert len(result1) == 64, f"hex digest SHA-256 deve ter 64 caracteres, mas tem {len(result1)}"
    assert all(c in "0123456789abcdef" for c in result1), "hex digest deve conter apenas caracteres hexadecimais"
