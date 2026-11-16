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

Or run everything in Docker with `make up-all` (api on :8000, web on :5173, worker, Postgres);
`make down` stops all of it. `make migrate` still runs from the host against the published port.

If port 5432 is taken on the host, set `POSTGRES_PORT` and the port in `DATABASE_URL` in `.env`
to another value; do not stop the other service.

## 3. Commands

| Command | Does | From phase |
| --- | --- | --- |
| `make up` / `make down` | start / stop Postgres | 1.1a |
| `make migrate` | apply Alembic migrations (creates the nine v1 tables) | 1.1a |
| `make up-all` | whole stack in Docker (postgres, api, worker, web) | 1.1a |
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
| `API_PROXY_TARGET` | `http://localhost:8000` | where the Vite dev server forwards `/api/*` (read by `web/vite.config.ts`) | 1.1a |
| `QUEUE_VISIBILITY_TIMEOUT_S` | `300` | a job in `running` longer than this goes back to the queue (its worker died) | 1.1a |
| `WORKER_POLL_INTERVAL_S` | `1.0` | seconds the worker sleeps when the queue is empty | 1.1a |
| `MIN_CHARS_PER_PAGE` | `100` | a PDF with fewer non-space characters per page on average is rejected as a scan | 1.1b |
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
| 1.1a | `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `psycopg[binary,pool]`, `alembic` | Docker image `pgvector/pgvector:pg17`; npm: `react`, `react-dom`, `@tanstack/react-query`; dev: `typescript`, `vite`, `@vitejs/plugin-react`, `@types/react`, `@types/react-dom`, `@types/node`, `eslint`, `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `globals` |
| 1.1b | `pymupdf` (`>=1.28,<2`, see below), `python-multipart`, `cyrtranslit`, `lingua-language-detector` | |
| 1.2 | `google-genai` | npm: `@tanstack/react-table` |
| 1.3 | eval group: `scikit-learn`, `scipy`, `statsmodels` | |
| 1.4b | `rapidfuzz` | |
| 1.6 | `langfuse` | Langfuse self-host: web, worker, Postgres, ClickHouse, Redis, MinIO |
| 1.7 | none | GitHub Actions |
| 2.1 | `sentence-transformers` (with CPU-only `torch`), `pgvector` | model `BAAI/bge-m3`, about 2.3 GB in the Hugging Face cache |
| 2.2 | none | model `BAAI/bge-reranker-v2-m3`, about 2.3 GB |
| 3.6 | `langgraph`, `langgraph-checkpoint-postgres`, `langchain`, `langchain-google-genai` | |
| 3.7 | `mcp` (version 2) | n8n in Docker (optional) |

`typescript-eslint` is pinned to exactly 8.72.0: the registry lists 8.73.0 but serves no tarball for
`@typescript-eslint/types@8.73.0` (404), so a fresh install of the latest fails. Move to a newer
release once it installs. `@emnapi/core` and `@emnapi/runtime` are pinned dev dependencies only to
work around an npm bug: the optional WASM fallback of rolldown (inside Vite) lists them, but npm
leaves them out of a lockfile made on Windows, and `npm ci` in the Linux image then fails.
Remove them when `npm ci` passes in `docker/web.Dockerfile` without them. `npm audit` reports advisories in the lint toolchain only (`minimatch`);
the production dependencies are clean.

Alembic brings in SQLAlchemy as its own dependency. It is used for migrations only; application
queries are raw SQL through psycopg 3.

`pymupdf` is capped below 2: version 2.x is a meta-package that also installs `pymupdf-layout`,
`pymupdf4llm`, `onnxruntime`, `numpy` and `networkx`, none of which 1.1b needs. Lift the cap
only if a later phase wants them.

PyMuPDF is AGPL-licensed. A closed commercial product needs a replacement or a commercial license (§6.3).

## 6. Machine state (changes outside the repository)

Claude Code logs here everything it creates or changes outside the repository, with the command that undoes it.

| Date | Change | Why | Undo |
| --- | --- | --- | --- |
| 2026-11-16 | Docker image `pgvector/pgvector:pg17`, network `ats_default`, volume `ats_pgdata` (compose project `ats`) | Postgres for phase 1.1a | `docker compose down -v` (deletes the data), then `docker rmi pgvector/pgvector:pg17` |
| 2026-11-16 | Docker images `ats-api`, `ats-worker`, `ats-web`, plus base images `python:3.12-slim`, `node:24-alpine` and `ghcr.io/astral-sh/uv:0.13.8` | `make up-all` (phase 1.1a) | `docker compose --profile full down --rmi local`, then `docker rmi python:3.12-slim node:24-alpine ghcr.io/astral-sh/uv:0.13.8` |
