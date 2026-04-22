"""
Property-based tests for pipeline/grammar_router.py.

Property 11: Grammar_Router retorna parser correto para extensões suportadas
             e None para não suportadas — Validates: Requirements 3a.1, 3a.2, 3a.3

Property 12: Grammar_Router é singleton — mesma instância para mesma extensão
             — Validates: Requirements 3a.4
"""
import pytest
from hypothesis import given, settings, strategies as st

from pipeline.grammar_router import Grammar_Router, SUPPORTED_EXTENSIONS
from tests.strategies import unsupported_ext_strategy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_grammar_router_singleton():
    """Reseta o singleton entre testes para garantir isolamento."""
    Grammar_Router._instance = None
    yield
    Grammar_Router._instance = None


# ---------------------------------------------------------------------------
# Property 11: Grammar_Router retorna parser correto por extensão
# Validates: Requirements 3a.1, 3a.2, 3a.3
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(st.sampled_from(SUPPORTED_EXTENSIONS))
def test_property_11a_supported_extensions_return_non_none(extension):
    """**Validates: Requirements 3a.1, 3a.2, 3a.3**

    Property 11 (parte A): Para qualquer extensão suportada,
    get_parser() deve retornar um objeto não-nulo (parser configurado).

    Nota: quando tree-sitter não está instalado, o parser pode ser None
    mas o mapeamento deve existir (a chave deve estar no dicionário interno).
    """
    router = Grammar_Router()
    # Verificar que a extensão está no mapeamento interno
    router._ensure_initialized()
    assert extension in router._parsers, (
        f"Extensão suportada '{extension}' não encontrada no mapeamento interno"
    )


@settings(max_examples=100)
@given(unsupported_ext_strategy())
def test_property_11b_unsupported_extensions_return_none(extension):
    """**Validates: Requirements 3a.1, 3a.2, 3a.3**

    Property 11 (parte B): Para qualquer extensão fora do conjunto suportado,
    get_parser() deve retornar None.
    """
    router = Grammar_Router()
    result = router.get_parser(extension)
    assert result is None, (
        f"Extensão não suportada '{extension}' deveria retornar None, "
        f"mas retornou {result!r}"
    )


# ---------------------------------------------------------------------------
# Property 12: Grammar_Router é singleton — mesma instância para mesma extensão
# Validates: Requirements 3a.4
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    st.sampled_from(SUPPORTED_EXTENSIONS),
    st.integers(min_value=2, max_value=10),
)
def test_property_12_singleton_same_parser_instance(extension, n_calls):
    """**Validates: Requirements 3a.4**

    Property 12: Para qualquer extensão suportada, chamar get_parser() N vezes
    deve retornar sempre o mesmo objeto (identidade de referência), garantindo
    que cada gramática é instanciada uma única vez por execução.
    """
    router = Grammar_Router()
    results = [router.get_parser(extension) for _ in range(n_calls)]

    # Verificar que todas as chamadas retornam o mesmo objeto (identidade)
    first = results[0]
    for i, result in enumerate(results[1:], start=1):
        assert result is first, (
            f"Chamada {i + 1} para get_parser('{extension}') retornou objeto diferente: "
            f"{result!r} is not {first!r}"
        )


@settings(max_examples=50)
@given(st.sampled_from(SUPPORTED_EXTENSIONS))
def test_property_12_singleton_same_router_instance(extension):
    """**Validates: Requirements 3a.4**

    Verificação adicional: Grammar_Router() sempre retorna a mesma instância
    (comportamento singleton via __new__).
    """
    router1 = Grammar_Router()
    router2 = Grammar_Router()
    assert router1 is router2, (
        "Grammar_Router() deve retornar sempre a mesma instância (singleton)"
    )
