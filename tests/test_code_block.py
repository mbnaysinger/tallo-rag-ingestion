"""
Property-based tests for Code_Block structural invariant.

**Validates: Requirements 3.7**
"""
from hypothesis import given, settings, strategies as st

from models.code_block import Code_Block


@settings(max_examples=100)
@given(
    st.text(min_size=1),
    st.text(min_size=1),
    st.text(min_size=1),
    st.integers(min_value=1),
    st.integers(min_value=1),
)
def test_property_9_code_block_structural_invariant(
    node_type, language, content, start_line, end_line_offset
):
    """Property 9: Invariante estrutural de Code_Block.

    Para qualquer instância de Code_Block com end_line >= start_line,
    todos os campos obrigatórios são não-nulos/não-vazios e
    start_line <= end_line é satisfeito.

    **Validates: Requirements 3.7**
    """
    # Garantir end_line >= start_line somando o offset (>= 0) ao start_line
    end_line = start_line + (end_line_offset - 1)  # end_line_offset >= 1, então end_line >= start_line

    block = Code_Block(
        node_type=node_type,
        language=language,
        content=content,
        start_line=start_line,
        end_line=end_line,
    )

    # Campos obrigatórios não-nulos e não-vazios
    assert block.node_type is not None and block.node_type != ""
    assert block.language is not None and block.language != ""
    assert block.content is not None and block.content != ""
    assert block.start_line is not None
    assert block.end_line is not None

    # Invariante: start_line <= end_line
    assert block.start_line <= block.end_line

    # metadata tem valor padrão de dict vazio
    assert isinstance(block.metadata, dict)
