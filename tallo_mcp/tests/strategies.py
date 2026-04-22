"""
Hypothesis strategies customizadas para os testes de propriedade do
Tallo RAG MCP Server.
"""
import sys
from pathlib import Path
from typing import Optional

from hypothesis import strategies as st

# Garante que a raiz do repositório está no sys.path
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tallo_mcp.db import FileBlock


# ---------------------------------------------------------------------------
# file_block_strategy
# ---------------------------------------------------------------------------

@st.composite
def file_block_strategy(draw):
    """Gera FileBlock com start_line <= end_line válidos."""
    file_path = draw(st.text(min_size=1, max_size=200).filter(lambda s: s.strip()))
    content = draw(st.text(min_size=0, max_size=500))
    block_id = draw(st.uuids().map(str))
    start_line = draw(st.integers(min_value=1, max_value=10_000))
    end_line = draw(st.integers(min_value=start_line, max_value=start_line + 500))
    language = draw(st.sampled_from(["python", "java", "javascript", "sql", "cfml", "html"]))
    node_type = draw(st.sampled_from([
        "function_definition", "class_definition", "method_declaration",
        "dml_statement", "ddl_statement", "arrow_function",
    ]))

    metadata = {
        "start_line": start_line,
        "end_line": end_line,
        "language": language,
        "node_type": node_type,
    }

    return FileBlock(
        id=block_id,
        content=content,
        file_path=file_path,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# indexed_record_strategy
# ---------------------------------------------------------------------------

@st.composite
def indexed_record_strategy(draw):
    """Gera registros com file_path, language e start_line para popular mock DB."""
    file_path = draw(
        st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="/_-."),
            min_size=1,
            max_size=100,
        ).filter(lambda s: s.strip())
    )
    language = draw(st.sampled_from(["python", "java", "javascript", "sql", "cfml", "html"]))
    start_line = draw(st.integers(min_value=1, max_value=10_000))
    block_id = draw(st.uuids().map(str))
    content = draw(st.text(min_size=0, max_size=200))

    return {
        "id": block_id,
        "file_path": file_path,
        "language": language,
        "start_line": start_line,
        "content": content,
    }


# ---------------------------------------------------------------------------
# tool_invocation_strategy
# ---------------------------------------------------------------------------

@st.composite
def tool_invocation_strategy(draw):
    """Gera invocações de tool com parâmetros válidos para testar logging."""
    tool_name = draw(st.sampled_from(["search_code", "get_file_blocks", "list_indexed_files"]))

    if tool_name == "search_code":
        query = draw(st.text(min_size=1, max_size=200))
        limit = draw(st.integers(min_value=1, max_value=50))
        language = draw(st.one_of(
            st.none(),
            st.sampled_from(["python", "java", "javascript", "sql"]),
        ))
        node_type = draw(st.one_of(
            st.none(),
            st.sampled_from(["function_definition", "class_definition", "method_declaration"]),
        ))
        params = {"query": query, "limit": limit, "language": language, "node_type": node_type}

    elif tool_name == "get_file_blocks":
        file_path = draw(st.text(min_size=1, max_size=200).filter(lambda s: s.strip()))
        params = {"file_path": file_path}

    else:  # list_indexed_files
        params = {}

    return {"tool_name": tool_name, "params": params}
