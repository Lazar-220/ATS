# Setup, dependencies and run commands

Claude Code keeps this file current: a phase that adds a dependency, a service, an environment
variable or a command updates it in the same commit. Sections 3 to 5 describe the target state;
a row marked with a phase exists only after that phase is merged.

## 1. Prerequisites (install once, by hand)

| Tool | Needed for | Check |
| --- | --- | --- |
| Git | version control | `git --version` |
| Docker Desktop or Docker Engine, with Compose v2 | Postgres, Langfuse, n8n | `docker compose version` |
| uv | Python 3.12+ and Python packages; also runs the Claude Code hooks | `uv --version` |
| Node.js LTS (22 or newer) with npm | the React frontend | `node --version` |
| make | the command contract | `make --version` |
| VS Code with the Claude Code extension | development | Extensions view |
| Claude Code CLI (standalone) | CLI-only features, `claude --resume` | `claude --version` |
| Gemini API key from Google AI Studio | all LLM calls | set as `LLM_API_KEY` |

Windows: work inside WSL2 (Ubuntu), with the repository on the Linux filesystem, and open it in
VS Code through the WSL extension. Docker Desktop already runs on WSL2, and `make` and the hooks
work there without changes. Cap WSL memory in `%UserProfile%\.wslconfig` so Windows stays usable (§6.3):

```ini
[wsl2]
memory=8GB
```

## 2. First run

```bash
cp .env.example .env        # then set LLM_API_KEY in .env yourself
uv sync                     # Python dependencies
npm install --prefix web    # frontend dependencies (from phase 1.1a)
make up                     # Postgres + pgvector in Docker
make migrate                # create the schema
```

Then, each in its own terminal:

```bash
make api        # http://localhost:8000  (OpenAPI at /docs)
make worker     # job worker
make web        # http://localhost:5173
```

Stop with `Ctrl+C` in each terminal, then `make down`.

## 3. Commands

| Command | Does | From phase |
| --- | --- | --- |
| `make up` / `make down` | start / stop Postgres | 1.1a |
| `make up-all` | whole stack in Docker (postgres, api, worker, web) | 1.1a |
| `make migrate` | apply Alembic migrations | 1.1a |
| `make api` | FastAPI with reload on :8000 | 1.1a |
| `make worker` | job worker | 1.1a |
| `make web` | Vite dev server on :5173 | 1.1a |
| `make check` | ruff, pyright, unit tests, web typecheck and lint | 0 |
| `make test` | unit tests | 0 |
| `make test-int` | integration tests (needs `make up`) | 1.1a |
| `make eval VARIANT=A SPLIT=dev` | eval harness | 1.3 |
| `make eval-redteam` | injection red-team set | 1.7 |
| `make langfuse-up` / `make langfuse-down` | Langfuse self-host (about 4 GB of RAM) | 1.6 |
| `make reindex` | re-chunk and re-embed every CV | 2.1 |
| `make mcp` | MCP server | 3.7 |

## 4. Environment variables

| Variable | Default | Meaning | From phase |
| --- | --- | --- | --- |
| `DATABASE_URL` | `postgresql://ats:ats@localhost:5432/ats` | Postgres connection; keep the port in step with `POSTGRES_PORT` | 1.1a |
| `POSTGRES_PORT` | `5432` | host port of the Postgres container; change it if 5432 is taken | 1.1a |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `ats` | credentials of the Postgres container | 1.1a |
| `DB_POOL_MAX_SIZE` | `5` | connection pool size per process | 1.1a |
| `UPLOAD_DIR` | `data/uploads` | stored PDFs | 1.1b |
| `LLM_MODEL` | `gemini-3.8-flash` | model for every LLM role | 1.2 |
| `LLM_API_KEY` | none | Gemini API key; never committed | 1.2 |
| `LLM_RPM` | `5` | requests per minute (free tier) | 1.2 |
| `LLM_CACHE_DIR` | `data/llm_cache` | LLM response cache | 1.2 |
| `LANGFUSE_ENABLED` | `false` | tracing on or off | 1.6 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | local embedding model | 2.1 |
| `RERANKER_MODEL` | empty (off) | local reranker | 2.2 |
| `ORCHESTRATOR` | `manual` | `manual` or `langgraph` | 3.6 |

## 5. Dependencies by phase

Planned from §6.3 of the plan. The actual pinned versions are in `pyproject.toml`, `uv.lock`,
`web/package.json` and `web/package-lock.json`.

| Phase | Python (`uv add`) | Other |
| --- | --- | --- |
| 0 | dev group: `ruff`, `pyright`, `pytest`, `pytest-asyncio`, `httpx` | |
| 1.1a | `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `psycopg[binary,pool]`, `alembic` | Docker image `pgvector/pgvector:pg17`; npm: `react`, `react-dom`, `typescript`, `vite`, `@tanstack/react-query` |
| 1.1b | `pymupdf`, `python-multipart`, `cyrtranslit`, `lingua-language-detector` | |
| 1.2 | `google-genai` | npm: `@tanstack/react-table` |
| 1.3 | eval group: `scikit-learn`, `scipy`, `statsmodels` | |
| 1.4b | `rapidfuzz` | |
| 1.6 | `langfuse` | Langfuse self-host: web, worker, Postgres, ClickHouse, Redis, MinIO |
| 1.7 | none | GitHub Actions |
| 2.1 | `sentence-transformers` (with CPU-only `torch`), `pgvector` | model `BAAI/bge-m3`, about 2.3 GB in the Hugging Face cache |
| 2.2 | none | model `BAAI/bge-reranker-v2-m3`, about 2.3 GB |
| 3.6 | `langgraph`, `langgraph-checkpoint-postgres`, `langchain`, `langchain-google-genai` | |
| 3.7 | `mcp` (version 2) | n8n in Docker (optional) |

Alembic brings in SQLAlchemy as its own dependency. It is used for migrations only; application
queries are raw SQL through psycopg 3.

PyMuPDF is AGPL-licensed. A closed commercial product needs a replacement or a commercial license (§6.3).

## 6. Machine state (changes outside the repository)

Claude Code logs here everything it creates or changes outside the repository, with the command that undoes it.

| Date | Change | Why | Undo |
| --- | --- | --- | --- |
| 2026-11-16 | Docker image `pgvector/pgvector:pg17`, network `ats_default`, volume `ats_pgdata` (compose project `ats`) | Postgres for phase 1.1a | `docker compose down -v` (deletes the data), then `docker rmi pgvector/pgvector:pg17` |
