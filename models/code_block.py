from dataclasses import dataclass, field


@dataclass
class Code_Block:
    node_type: str           # ex: "method_declaration", "sql_injection"
    language: str            # ex: "java", "sql", "cfml"
    content: str             # texto completo do bloco
    start_line: int
    end_line: int
    metadata: dict = field(default_factory=dict)
    # metadata pode conter: imports (Java), sql_dialect, block_type (ddl/dml),
    # injection_source_line (sql_injection), file_sha256
