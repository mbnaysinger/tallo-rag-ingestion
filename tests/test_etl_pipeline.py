"""
Testes de propriedade para ETL_Pipeline.

Property 1: Descoberta recursiva retorna exatamente os arquivos suportados
  Validates: Requirements 1.1

Property 23: Sumário do job é internamente consistente
  Validates: Requirements 8.3
"""
import tempfile
from pathlib import Path
from hypothesis import given, settings

from pipeline.etl_pipeline import ETL_Pipeline
from pipeline.grammar_router import SUPPORTED_EXTENSIONS
from tests.strategies import directory_structure_strategy, job_summary_strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pipeline() -> ETL_Pipeline:
    """Cria um ETL_Pipeline com settings e job_store mínimos (sem conexão real)."""

    class _FakeSettings:
        openai_api_key = "fake-key"
        db_host = "localhost"
        db_port = 5432
        db_name = "test"
        db_user = "test"
        db_password = "test"
        sql_dialect = "unknown"

    # Patch __init__ to avoid real connections during unit tests
    pipeline = object.__new__(ETL_Pipeline)
    pipeline._settings = _FakeSettings()
    pipeline._job_store = {}
    # We only need _discover_files, so skip instantiating heavy components
    from pipeline.grammar_router import Grammar_Router
    from pipeline.parser import Parser
    from pipeline.deduplicator import Deduplicator
    pipeline._grammar_router = Grammar_Router()
    pipeline._parser = Parser()
    pipeline._deduplicator = Deduplicator()
    # embedding_client and vector_store are not needed for _discover_files
    pipeline._embedding_client = None  # type: ignore[assignment]
    pipeline._vector_store = None  # type: ignore[assignment]
    return pipeline  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Property 1: Descoberta recursiva retorna exatamente os arquivos suportados
# Validates: Requirements 1.1
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(directory_structure_strategy())
def test_property_1_discover_files_returns_exactly_supported(structure):
    """**Validates: Requirements 1.1**

    Property 1: Para qualquer estrutura de diretório, _discover_files retorna
    exatamente o conjunto de arquivos com extensões suportadas — nem mais, nem menos.
    """
    supported_files, unsupported_files = structure

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create all files in tmp_path
        created_supported: list[Path] = []
        for rel_path in supported_files:
            full_path = tmp_path / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text("content")
            created_supported.append(full_path)

        for rel_path in unsupported_files:
            full_path = tmp_path / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text("content")

        pipeline = _make_pipeline()
        discovered = pipeline._discover_files(tmp_path)

        # Must return exactly the supported files (as a set, order may vary)
        assert set(discovered) == set(created_supported), (
            f"Expected {set(created_supported)}, got {set(discovered)}"
        )

        # All returned files must have supported extensions
        supported_set = set(SUPPORTED_EXTENSIONS)
        for f in discovered:
            assert f.suffix.lower() in supported_set, (
                f"File {f} has unsupported extension {f.suffix}"
            )


# ---------------------------------------------------------------------------
# Property 23: Sumário do job é internamente consistente
# Validates: Requirements 8.3
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(job_summary_strategy())
def test_property_23_job_summary_internally_consistent(summary):
    """**Validates: Requirements 8.3**

    Property 23: Para qualquer sumário de job, deve valer:
      files_discovered >= files_processed + files_skipped + files_failed
      elapsed_seconds >= 0
    """
    assert summary["files_discovered"] >= (
        summary["files_processed"] + summary["files_skipped"] + summary["files_failed"]
    ), (
        f"files_discovered ({summary['files_discovered']}) < "
        f"processed + skipped + failed "
        f"({summary['files_processed']} + {summary['files_skipped']} + {summary['files_failed']})"
    )

    assert summary["elapsed_seconds"] >= 0, (
        f"elapsed_seconds must be >= 0, got {summary['elapsed_seconds']}"
    )
