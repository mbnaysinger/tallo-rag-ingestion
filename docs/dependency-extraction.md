# Dependency Extraction

## Overview

By default, the ingestion pipeline stores each code block as an independent unit. This works well for semantic search, but loses the structural relationships between files — a `Controller` that injects a `Service`, which calls a `Repository`, which maps to an `Entity`.

Dependency extraction enriches the `metadata` JSONB field of each `Code_Block` at parse time, enabling the MCP server to reconstruct those chains at query time without re-reading source files.

---

## What gets extracted

### Java

Every `class_declaration` block gains:

| Field | Description | Example |
|---|---|---|
| `class_name` | Name of the declared class | `"OrderController"` |
| `extends` | Parent class name | `"BaseController"` |
| `implements` | List of implemented interfaces | `["Serializable"]` |
| `annotations` | Class-level annotations | `["@RequestScoped", "@Path(\"/order\")"]` |
| `injects` | Types of fields annotated with `@Inject` | `["OrderTransaction", "OrderRepository"]` |
| `imports` | Raw import statements | `["import com.example.OrderTransaction"]` |

Every `method_declaration` block gains:

| Field | Description | Example |
|---|---|---|
| `method_name` | Name of the method | `"processOrder"` |
| `return_type` | Return type | `"OrderVoImpl"` |
| `param_types` | List of parameter types | `["OrderVoImpl"]` |
| `annotations` | Method-level annotations | `["@POST", "@Path(\"/process\")"]` |
| `calls` | Deduplicated method invocations inside the body | `["this.orderTransaction.process", "LOGGER.log"]` |
| `imports` | Raw import statements (file-level) | `[...]` |

**Example metadata — Java class block:**
```json
{
  "class_name": "OrderController",
  "extends": "BaseController",
  "implements": ["Serializable"],
  "annotations": ["@RequestScoped", "@Path(\"/order\")"],
  "injects": ["OrderTransaction", "OrderRepository"],
  "imports": ["import com.example.order.OrderTransaction", "..."]
}
```

**Example metadata — Java method block:**
```json
{
  "method_name": "processOrder",
  "return_type": "OrderVoImpl",
  "param_types": ["OrderVoImpl"],
  "annotations": ["@POST", "@Path(\"/process\")"],
  "calls": ["this.orderTransaction.process", "LOGGER.log"],
  "imports": ["..."]
}
```

---

### CFML

Every `cffunction` block gains:

| Field | Description | Example |
|---|---|---|
| `function_name` | Value of the `name` attribute | `"selecionarRegra"` |
| `component_name` | Name of the enclosing `cfcomponent` (or filename stem) | `"RegraAnaliseCredito"` |
| `return_type` | Value of the `returntype` attribute | `"query"` |
| `calls_components` | Components referenced via `cfinvoke` or `new ComponentName()` | `["ConcessaoCredito", "ClienteRestricao"]` |

Every `sql_injection` block gains:

| Field | Description | Example |
|---|---|---|
| `tables` | Table names extracted from `FROM`, `JOIN`, `INTO`, `UPDATE` clauses | `["REGRA_REANALISE_CREDITO", "CLIENTE"]` |
| `component_name` | Name of the enclosing component | `"RegraAnaliseCredito"` |
| `sql_dialect` | Dialect configured via `SQL_DIALECT` env var | `"sybase"` |

**Example metadata — CFML function block:**
```json
{
  "function_name": "selecionarRegraAnalise",
  "component_name": "RegraAnaliseCredito",
  "return_type": "query",
  "calls_components": ["ConcessaoCredito"]
}
```

**Example metadata — sql_injection block:**
```json
{
  "component_name": "RegraAnaliseCredito",
  "tables": ["REGRA_REANALISE_CREDITO"],
  "sql_dialect": "sybase",
  "injection_source_line": 16
}
```

---

### JSX / TSX

Every `function_declaration` block gains:

| Field | Description | Example |
|---|---|---|
| `component_name` | Function identifier | `"OrderForm"` |
| `imports` | File-level import statements | `["import { useOrder } from './hooks'"]` |
| `hooks` | React hooks called inside the function | `["useState", "useOrder"]` |

Every `arrow_function` block gains:

| Field | Description | Example |
|---|---|---|
| `imports` | File-level import statements | `[...]` |
| `hooks` | React hooks called inside the function | `["useEffect"]` |

---

## Database

The new fields are stored inside the existing `metadata JSONB` column — no schema changes required.

A GIN index is added by migration `002` to make filtering on these fields efficient:

```sql
-- db/migrations/002_add_gin_index_metadata.sql
CREATE INDEX IF NOT EXISTS idx_code_embeddings_metadata_gin
    ON code_embeddings
    USING gin (metadata jsonb_path_ops);
```

Apply it once:

```bash
psql -h $DB_HOST -U $DB_USER -d $DB_NAME \
  -f db/migrations/002_add_gin_index_metadata.sql
```

---

## Re-ingesting existing data

Because the new metadata fields are populated at parse time, existing records in the database do not have them. You need to truncate and re-ingest:

```bash
# Clear all records
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "TRUNCATE code_embeddings;"

# Or clear only a specific project
psql -h $DB_HOST -U $DB_USER -d $DB_NAME \
  -c "DELETE FROM code_embeddings WHERE file_path LIKE '/path/to/project%';"

# Then re-ingest via the API
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"repository_path": "/path/to/project"}'
```

---

## MCP — `search_code` with dependency expansion

The `search_code` tool accepts two new optional parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `expand_dependencies` | `bool` | `false` | When `true`, resolves and returns dependent blocks alongside primary results |
| `dependency_depth` | `int` | `1` | How many levels of the dependency chain to follow (1–3) |

### How resolution works

| Language | Source field | Resolved via |
|---|---|---|
| Java | `injects`, `extends`, `implements` | `metadata->>'class_name'` |
| CFML | `calls_components` | `metadata->>'component_name'` |

The resolution is purely metadata-based — no re-embedding, no extra OpenAI calls.

### Response structure

Primary results (from semantic search) include a `score` field.
Dependency blocks include `"_dependency": true` and `score: null`.

```json
[
  {
    "id": "...",
    "content": "public class OrderController { ... }",
    "file_path": "/src/.../OrderController.java",
    "score": 0.12,
    "metadata": {
      "class_name": "OrderController",
      "injects": ["OrderTransaction", "OrderRepository"],
      ...
    }
  },
  {
    "id": "...",
    "content": "public class OrderTransaction { ... }",
    "file_path": "/src/.../OrderTransaction.java",
    "score": null,
    "_dependency": true,
    "metadata": {
      "class_name": "OrderTransaction",
      "injects": ["OrderRepository"],
      ...
    }
  },
  {
    "id": "...",
    "content": "public class OrderRepository { ... }",
    "file_path": "/src/.../OrderRepository.java",
    "score": null,
    "_dependency": true,
    "metadata": {
      "class_name": "OrderRepository",
      ...
    }
  }
]
```

### Example — depth 2 chain

With `dependency_depth=2`, a search for `"order processing"` that returns `OrderController` will also pull `OrderTransaction` (depth 1) and then `OrderRepository` (depth 2), giving the LLM the full call chain in a single tool invocation.

### Limits

- `dependency_depth` is capped at 3 to avoid runaway queries on large codebases.
- Circular dependencies (A → B → A) are handled via a `seen_ids` set — each block appears at most once in the response.
- If a referenced class/component is not indexed, it is silently skipped.
