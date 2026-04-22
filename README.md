# Tallo RAG

Tallo RAG é um sistema de busca semântica de código-fonte composto por dois serviços:

- **Ingestion Service** — percorre repositórios locais, extrai blocos lógicos de código via Tree-sitter, gera embeddings com `text-embedding-3-large` e persiste no pgvector.
- **MCP Server** — expõe ferramentas de consulta semântica via [Model Context Protocol](https://modelcontextprotocol.io/), permitindo que LLMs (Claude, Kiro, etc.) consultem o banco de embeddings diretamente.

---

## Pré-requisitos

- Python 3.11+
- PostgreSQL com extensão [pgvector](https://github.com/pgvector/pgvector)
- Chave de API OpenAI (ou Azure OpenAI)

---

## Configuração

Copie o arquivo de exemplo e preencha as variáveis:

```bash
cp .env.example .env
```

### Variáveis de Ambiente

| Variável                   | Obrigatória | Descrição                                          | Padrão                   |
|----------------------------|-------------|----------------------------------------------------|--------------------------|
| `OPENAI_API_KEY`           | Sim         | Chave de API OpenAI                                | —                        |
| `DB_HOST`                  | Sim         | Host do PostgreSQL                                 | —                        |
| `DB_PORT`                  | Sim         | Porta do PostgreSQL                                | —                        |
| `DB_NAME`                  | Sim         | Nome do banco de dados                             | —                        |
| `DB_USER`                  | Sim         | Usuário do banco                                   | —                        |
| `DB_PASSWORD`              | Sim         | Senha do banco                                     | —                        |
| `SQL_DIALECT`              | Não         | Dialeto SQL: `sybase`, `oracle`, `sqlserver`       | `unknown`                |
| `AZURE_OPENAI_ENDPOINT`    | Não         | Endpoint Azure OpenAI (ativa cliente Azure)        | —                        |
| `AZURE_OPENAI_API_VERSION` | Não         | Versão da API Azure OpenAI                         | `2023-05-15`             |
| `AZURE_OPENAI_DEPLOYMENT`  | Não         | Nome do deployment Azure                           | `text-embedding-3-large` |

### Banco de Dados

Execute a migration para criar a tabela e os índices:

```bash
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f db/migrations/001_create_code_embeddings.sql
```

---

## Ingestion Service

### Instalação

```bash
pip install -r requirements.txt
```

### Executando

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Linguagens Suportadas

| Extensão          | Linguagem  | Blocos Extraídos                                          |
|-------------------|------------|-----------------------------------------------------------|
| `.java`           | Java       | `method_declaration`, `class_declaration`                 |
| `.jsx`, `.tsx`    | JavaScript | `function_declaration`, `arrow_function`, `jsx_element`   |
| `.html`           | HTML       | `element` (nível superior)                                |
| `.cfm`, `.cfc`    | CFML       | `cfcomponent`, `cffunction`, `cfquery`, `sql_injection`   |
| `.sql`            | SQL        | `ddl_statement`, `dml_statement`                          |

### Endpoints

#### `POST /ingest`

Inicia a ingestão assíncrona de um repositório. Retorna imediatamente com um `job_id`.

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"repository_path": "/Volumes/mbritz/_tree_sitter_project/my-repo"}'
```

**Resposta (HTTP 202):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

---

#### `GET /ingest/{job_id}/status`

Consulta o status e métricas de um job em andamento ou concluído.

```bash
curl http://localhost:8000/ingest/550e8400-e29b-41d4-a716-446655440000/status
```

**Resposta (HTTP 200):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "metrics": {
    "files_discovered": 142,
    "files_processed": 138,
    "files_skipped": 3,
    "files_failed": 1,
    "blocks_inserted": 1847,
    "elapsed_seconds": 34.21
  }
}
```

Valores possíveis de `status`: `pending` | `running` | `completed` | `failed`

---

#### `GET /health`

Verifica conectividade com PostgreSQL e configuração da API OpenAI.

```bash
curl http://localhost:8000/health
```

**Resposta (HTTP 200):**

```json
{
  "db": "healthy",
  "openai": "healthy"
}
```

---

### Coleção Postman

Importe o JSON abaixo no Postman (File → Import → Raw text):

```json
{
  "info": {
    "name": "Tallo RAG Ingestion",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "variable": [
    { "key": "base_url", "value": "http://localhost:8000" },
    { "key": "job_id",   "value": "" }
  ],
  "item": [
    {
      "name": "Start Ingestion",
      "request": {
        "method": "POST",
        "url": "{{base_url}}/ingest",
        "header": [{ "key": "Content-Type", "value": "application/json" }],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"repository_path\": \"/path/to/your/repo\"\n}"
        }
      }
    },
    {
      "name": "Get Job Status",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/ingest/{{job_id}}/status"
      }
    },
    {
      "name": "Health Check",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/health"
      }
    }
  ]
}
```

---

## MCP Server

O MCP Server expõe três ferramentas para consulta semântica ao banco de embeddings. Ele é iniciado como subprocesso pelo cliente MCP via transporte `stdio`.

### Instalação

```bash
pip install -r tallo_mcp/requirements.txt
```

### Configuração no Kiro / Claude Desktop

Adicione ao seu `mcp.json`:

```json
{
  "mcpServers": {
    "tallo-rag": {
      "command": "python",
      "args": ["-m", "tallo_mcp.server"],
      "cwd": "/caminho/para/tallo-rag-ingestion",
      "env": {
        "PYTHONPATH": "/caminho/para/tallo-rag-ingestion"
      }
    }
  }
}
```

Ou usando `python` diretamente:

```bash
python tallo_mcp/server.py
```

---

### Ferramentas MCP

#### `search_code`

Busca blocos de código semanticamente similares a uma query em linguagem natural ou código.

**Parâmetros:**

| Parâmetro   | Tipo     | Obrigatório | Descrição                                              | Padrão |
|-------------|----------|-------------|--------------------------------------------------------|--------|
| `query`     | `string` | Sim         | Texto ou trecho de código para busca semântica         | —      |
| `limit`     | `int`    | Não         | Número máximo de resultados (1–50)                     | `10`   |
| `language`  | `string` | Não         | Filtra por linguagem: `java`, `sql`, `cfml`, etc.      | `null` |
| `node_type` | `string` | Não         | Filtra por tipo: `method_declaration`, `cfquery`, etc. | `null` |

**Retorno:**

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "content": "public void processOrder(Order order) {\n    // ...\n}",
    "file_path": "/src/main/java/com/example/OrderService.java",
    "score": 0.142,
    "metadata": {
      "node_type": "method_declaration",
      "language": "java",
      "start_line": 42,
      "end_line": 67,
      "file_sha256": "e3b0c44298fc1c149afb...",
      "imports": ["java.util.List", "com.example.Order"]
    }
  }
]
```

> `score` é a distância coseno — valores menores indicam maior similaridade (0 = idêntico).

---

#### `get_file_blocks`

Retorna todos os blocos indexados de um arquivo específico, ordenados por linha de início.

**Parâmetros:**

| Parâmetro   | Tipo     | Obrigatório | Descrição                        |
|-------------|----------|-------------|----------------------------------|
| `file_path` | `string` | Sim         | Caminho completo do arquivo      |

**Retorno:**

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "content": "SELECT * FROM orders WHERE status = 'pending'",
    "file_path": "/src/queries/orders.sql",
    "metadata": {
      "node_type": "dml_statement",
      "language": "sql",
      "start_line": 1,
      "end_line": 3,
      "file_sha256": "a1b2c3...",
      "sql_dialect": "sybase",
      "block_type": "dml_statement"
    }
  }
]
```

> O campo `embedding` não é retornado nesta tool.

---

#### `list_indexed_files`

Lista todos os arquivos únicos indexados no banco, com contagem de blocos e linguagem detectada.

**Parâmetros:** nenhum

**Retorno:**

```json
[
  {
    "file_path": "/src/main/java/com/example/OrderService.java",
    "block_count": 12,
    "language": "java"
  },
  {
    "file_path": "/src/queries/orders.sql",
    "block_count": 8,
    "language": "sql"
  }
]
```

> Resultados ordenados alfabeticamente por `file_path`.

---

## Testes

### Ingestion Service

```bash
# Testes unitários e de propriedade
pytest tests/ -v

# Com cobertura
pytest tests/ --cov=. --cov-report=html
```

### MCP Server

```bash
# Testes unitários e de propriedade
pytest tallo_mcp/tests/ -v

# Com cobertura
pytest tallo_mcp/tests/ --cov=tallo_mcp --cov-report=html
```

---

## Arquitetura

```
tallo-rag-ingestion/
├── main.py                    # Entrypoint FastAPI
├── config.py                  # Carregamento de variáveis de ambiente
├── api/
│   ├── routes.py              # Endpoints REST
│   └── schemas.py             # Pydantic models
├── pipeline/
│   ├── etl_pipeline.py        # Orquestrador principal
│   ├── grammar_router.py      # Singleton de gramáticas Tree-sitter
│   ├── parser.py              # Extração de blocos por linguagem
│   ├── deduplicator.py        # SHA-256 para deduplicação
│   ├── embedding_client.py    # Batch OpenAI com retry
│   └── vector_store.py        # psycopg v3 + pgvector
├── models/
│   └── code_block.py          # Dataclass Code_Block
├── tallo_mcp/
│   ├── server.py              # FastMCP app + tool definitions
│   ├── db.py                  # Queries de leitura (MCP_VectorStore)
│   └── config.py              # load_mcp_settings()
├── db/
│   └── migrations/
│       └── 001_create_code_embeddings.sql
└── utils/
    └── logging.py             # Logging estruturado JSON
```

---

## Licença

MIT
