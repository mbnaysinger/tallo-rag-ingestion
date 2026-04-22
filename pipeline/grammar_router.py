"""
Grammar_Router — singleton que mapeia extensões de arquivo para parsers Tree-sitter.

Requirements: 3a.1, 3a.2, 3a.3, 3a.4
"""
from typing import Optional

# Importações condicionais para tree-sitter e gramáticas
try:
    from tree_sitter import Parser as TSParser, Language
    _TREE_SITTER_AVAILABLE = True
except ImportError:
    _TREE_SITTER_AVAILABLE = False
    TSParser = None  # type: ignore[assignment,misc]
    Language = None  # type: ignore[assignment]

try:
    import tree_sitter_java as _ts_java
    _JAVA_AVAILABLE = True
except ImportError:
    _JAVA_AVAILABLE = False
    _ts_java = None  # type: ignore[assignment]

try:
    import tree_sitter_javascript as _ts_javascript
    _JAVASCRIPT_AVAILABLE = True
except ImportError:
    _JAVASCRIPT_AVAILABLE = False
    _ts_javascript = None  # type: ignore[assignment]

try:
    import tree_sitter_html as _ts_html
    _HTML_AVAILABLE = True
except ImportError:
    _HTML_AVAILABLE = False
    _ts_html = None  # type: ignore[assignment]

try:
    import tree_sitter_cfml as _ts_cfml
    _CFML_AVAILABLE = True
except ImportError:
    _CFML_AVAILABLE = False
    _ts_cfml = None  # type: ignore[assignment]
try:
    import tree_sitter_sql as _ts_sql
    _SQL_AVAILABLE = True
except ImportError:
    _SQL_AVAILABLE = False
    _ts_sql = None  # type: ignore[assignment]


SUPPORTED_EXTENSIONS = [".java", ".jsx", ".tsx", ".html", ".cfm", ".cfc", ".sql"]


class _CfmlFallbackParser:
    """Parser de fallback para CFML usando regex, quando tree-sitter-cfml não está disponível."""

    def parse(self, content_bytes: bytes):
        import re
        content = content_bytes.decode("utf-8", errors="replace")
        # Simula a estrutura de árvore esperada pelo Parser._parse_cfml
        return _CfmlFakeTree(content)


class _CfmlFakeNode:
    def __init__(self, node_type, start_byte, end_byte, start_row, end_row, children=None):
        self.type = node_type
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.start_point = (start_row, 0)
        self.end_point = (end_row, 0)
        self.children = children or []


class _CfmlFakeTree:
    def __init__(self, content: str):
        import re
        nodes = []
        lines = content.split("\n")

        def byte_offset(row):
            return sum(len(l) + 1 for l in lines[:row])

        # Match cfcomponent, cffunction, cfquery tags (opening tags)
        patterns = [
            ("cfcomponent", re.compile(r"<cfcomponent\b", re.IGNORECASE)),
            ("cffunction",  re.compile(r"<cffunction\b",  re.IGNORECASE)),
            ("cfquery",     re.compile(r"<cfquery\b",     re.IGNORECASE)),
        ]

        for row, line in enumerate(lines):
            for node_type, pattern in patterns:
                if pattern.search(line):
                    start_byte = byte_offset(row)
                    # Find closing tag
                    close_tag = f"</{node_type}>"
                    end_row = row
                    for i in range(row, len(lines)):
                        if close_tag.lower() in lines[i].lower():
                            end_row = i
                            break

                    end_byte = byte_offset(end_row) + len(lines[end_row])
                    block_content = "\n".join(lines[row:end_row + 1])

                    children = []
                    if node_type == "cfquery":
                        # Extract SQL text between tags
                        inner_match = re.search(r"<cfquery[^>]*>(.*?)</cfquery>",
                                                block_content, re.DOTALL | re.IGNORECASE)
                        if inner_match:
                            sql_start = start_byte + inner_match.start(1)
                            sql_end = start_byte + inner_match.end(1)
                            text_node = _CfmlFakeNode("text", sql_start, sql_end, row, end_row)
                            children = [text_node]

                    nodes.append(_CfmlFakeNode(node_type, start_byte, end_byte, row, end_row, children))

        root = _CfmlFakeNode("document", 0, len(content), 0, len(lines) - 1, nodes)
        self.root_node = root


def _build_parser(grammar_module) -> Optional["TSParser"]:
    """Constrói um TSParser configurado com a linguagem do módulo de gramática."""
    if not _TREE_SITTER_AVAILABLE or grammar_module is None:
        return None
    try:
        # API tree-sitter >= 0.22: Parser recebe Language direto no construtor
        lang = Language(grammar_module.language())
        return TSParser(lang)
    except TypeError:
        pass
    except Exception:
        pass
    try:
        # API tree-sitter 0.21.x: Parser() + set_language()
        lang = Language(grammar_module.language())
        parser = TSParser()
        parser.set_language(lang)
        return parser
    except Exception:
        pass
    try:
        # API tree-sitter < 0.20: Language(ptr, name)
        lang = Language(grammar_module.language(), grammar_module.__name__.split("_", 2)[-1])
        parser = TSParser()
        parser.set_language(lang)
        return parser
    except Exception:
        return None


class Grammar_Router:
    """Singleton: instancia cada gramática uma única vez por execução.

    Requirements: 3a.1, 3a.2, 3a.3, 3a.4
    """

    _instance: Optional["Grammar_Router"] = None

    def __new__(cls) -> "Grammar_Router":
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._parsers: dict = {}  # type: ignore[attr-defined]
            instance._initialized = False  # type: ignore[attr-defined]
            cls._instance = instance
        return cls._instance

    def _ensure_initialized(self) -> None:
        """Inicializa os parsers na primeira chamada (lazy init)."""
        if self._initialized:
            return

        # Construir parsers uma única vez
        java_parser = _build_parser(_ts_java) if _JAVA_AVAILABLE else None
        js_parser = _build_parser(_ts_javascript) if _JAVASCRIPT_AVAILABLE else None
        html_parser = _build_parser(_ts_html) if _HTML_AVAILABLE else None
        cfml_parser = _build_parser(_ts_cfml) if _CFML_AVAILABLE else _CfmlFallbackParser()
        sql_parser = _build_parser(_ts_sql) if _SQL_AVAILABLE else None

        # Mapeamento estático de extensões para parsers (reutilizando instâncias)
        self._parsers = {
            ".java": java_parser,
            ".jsx": js_parser,
            ".tsx": js_parser,
            ".html": html_parser,
            ".cfm": cfml_parser,
            ".cfc": cfml_parser,
            ".sql": sql_parser,
        }
        self._initialized = True

    def get_parser(self, extension: str) -> Optional["TSParser"]:
        """Retorna Parser Tree-sitter configurado para a extensão.

        Retorna None se a extensão não for suportada ou se a gramática
        não estiver disponível.

        Requirements: 3a.2, 3a.3
        """
        self._ensure_initialized()
        return self._parsers.get(extension, None)
