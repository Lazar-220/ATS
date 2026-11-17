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

### Try the API (from phase 1.1b)

With `make api` and `make worker` running. Upload one posting and one or more CVs; the call
returns at once and the worker does the rest:

```bash
curl -i -F posting=@posting.pdf -F cvs=@cv_ana.pdf -F cvs=@cv_bojan.pdf http://localhost:8000/rankings
# HTTP/1.1 202 Accepted
# {"request_id":"103e1486-7484-4063-9049-f1699717e194","position_id":"7208d077-a80a-4c0e-af0e-1f2fcf06ff62"}
```

Read the status as often as you like; it changes nothing:

```bash
curl http://localhost:8000/rankings/103e1486-7484-4063-9049-f1699717e194
# {"request_id":"103e...","position_id":"7208...","status":"done","documents":[
#   {"document_id":"5102...","kind":"posting","filename":"posting.pdf","status":"extracted","message":null},
#   {"document_id":"c763...","kind":"cv","filename":"cv_ana.pdf","status":"extracted","message":null},
#   {"document_id":"288c...","kind":"cv","filename":"cv_scan.pdf","status":"rejected",
#    "message":"The PDF contains little or no selectable text and looks like a scan. ..."}]}
```

Request `status` is `queued` (no document picked up yet), `running`, `done` (every document is
extracted or rejected), or `failed` (the posting itself was rejected or failed). It is computed
from the documents at read time. A document is `uploaded`, `extracted`, `rejected` (a scan,
an unreadable or password-protected PDF; re-uploading it gives the same result) or `failed`
(unexpected error; uploading the same file again retries it). Errors: 422 for a file that is not a
PDF or is already stored as the other kind, 413 above `MAX_UPLOAD_MB`, 404 for an unknown request.

### Review the requirements (from phase 1.2)

When a new posting has been extracted, the worker makes one LLM call and writes the position's
requirements with status `unconfirmed`. Needs `LLM_API_KEY` in `.env`. The same posting uploaded
again is recognised by its `sha256` and costs nothing.

```bash
curl http://localhost:8000/positions
# [{"id":"7208...","filename":"posting.pdf","rubric_status":"unconfirmed","rubric_version":1,
#   "created_at":"...","requirement_count":5,"setup_status":"done","setup_message":null}]
curl http://localhost:8000/positions/7208d077-a80a-4c0e-af0e-1f2fcf06ff62
# the same fields plus "requirements":[{"id":"...","parent_id":null,"text":"Java","kind":"mandatory",
#   "weight":1,"min_months":null}, ...]  (the current rubric version only)
```

`setup_status` is `pending` (posting text not extracted yet), `running`, `done`, or `failed`
(`setup_message` says why: a rejected posting, or the extraction job ran out of attempts).

Endpoint 3 takes two kinds of answer. `rubric_version` is the version HR was looking at; a
different current version gives 409. `dedup_key` is chosen by the client per intent; a repeat with
the same key and body returns the first result with `"duplicate": true` and does nothing again,
while the same key with a different body gives 409.

```bash
# Confirm: sets rubric_status to "confirmed"
curl -X POST http://localhost:8000/hr/answers -H 'Content-Type: application/json' -d '{
  "type": "confirm", "position_id": "7208...", "dedup_key": "any-unique-string", "rubric_version": 1}'
# Edit: replaces the whole list, bumps rubric_version by one, enqueues one "rejudge" job per
# assessment of the position (handled from phase 1.4b). Does not change rubric_status.
# "id" and "parent" are labels inside this list; "parent" refers to another item's "id".
curl -X POST http://localhost:8000/hr/answers -H 'Content-Type: application/json' -d '{
  "type": "edit", "position_id": "7208...", "dedup_key": "another-unique-string", "rubric_version": 1,
  "requirements": {"requirements": [
    {"id": 1, "text": "Java", "kind": "mandatory", "weight": 3, "min_months": null, "parent": null},
    {"id": 2, "text": "3 years of Java", "kind": "mandatory", "weight": 3, "min_months": 36, "parent": 1}]}}'
# {"position_id":"7208...","rubric_version":2,"rubric_status":"unconfirmed","rejudge_jobs":0,"duplicate":false}
```

Weights are integers from 1 to 5; `kind` is `mandatory` or `nice_to_have`; the list must not be empty
and its parent links must not form a cycle (422 otherwise).

One real call to the model (synthetic posting, one request of the free quota), never run by
`make test` or `make check`:

```bash
uv run pytest -m llm -s tests/test_llm_smoke.py
```

### Positions that never got a setup job

A position whose posting was ingested before phase 1.2 (or by a worker without the setup handler)
stays `pending` in the screen. `make setup-missing` finds such positions, meaning posting text, no
requirements and no `position_setup` job, and by default only lists them and the number of LLM
calls the worker would make. Nothing is enqueued until `YES=1`; the worker then makes one call per
position, so check its `llm_model` in the startup line first.

```bash
make setup-missing                              # list
make setup-missing POSITION=efc50a1d YES=1      # enqueue one position
```

A position whose setup job exists but `failed` is not listed: upload its posting again to retry it.

### Is the worker running current code?

A process keeps the code it started with, so a worker left over from before a branch switch or a
`git pull` looks healthy and quietly lacks newer job types. Its first log line says what it is:

```
worker starting: code=phase/1.2-requirements@7837fa7 schema=0003 handlers=ingest,noop,position_setup llm_model=gemini-3.6-flash llm_rpm=5 llm_key=set
```

Compare `code=` with `git log -1`, `schema=` with `uv run alembic heads`, and `handlers=` with the
job types you expect (`position_setup` from phase 1.2). `-dirty` means tracked files had uncommitted
changes when it started. Restart the worker after changing worker code; `make worker` does not reload.

### CV parsing in the worker (from phase 1.4a)

The ingest job now carries a CV past text extraction: it masks name, email, phone and address
(`document.masked_text`, the replaced raw ranges in `document.mask_spans`), makes one LLM call on
the masked text, and stores the parsed items with snippet positions, months per item and total
tenure in `document.parsed_json`, and the flags (`not_a_cv`, `suspected_injection`,
`low_coverage`) in `document.flags`. The document ends as `parsed`. The original contact data is
written to `candidate` only for a document the model judged to be a CV. This needs `LLM_API_KEY`
in the worker's environment; one CV is one call (cached by the response cache). A worker that
started before this phase does not know the step: restart it (`schema=0003` in its first log line).

### Judging and scoring in the worker (from phase 1.4b)

When a CV is parsed and its position has requirements, the worker makes one judge call per
candidate-position pair (`judge` job; more only if the answer lacks a requirement or has one
twice: then one more call, then the job fails). Code checks each quote against the CV, computes the
score and stores one `assessment` with a `verdict` per requirement. Either arrival (CV parsed, or
requirements ready) can come last; the job's dedup key `judge:<candidate>:<position>:<rubric_version>`
makes the second one a no-op. The same CV and posting submitted again make no LLM call. An edit of
the requirements enqueues `rejudge` jobs, which judge the assessment again in place. A job that
runs out of attempts leaves the assessment `failed` (upload the CV again to retry). Request status is
`done` only when every CV that has a candidate has an assessment (`done` or `failed`), and `failed`
also when the position's requirement setup failed. A worker that started before this phase does not
know `judge` or `rejudge` (check `handlers=` in its first log line).

## 3. Commands

| Command | Does | From phase |
| --- | --- | --- |
| `make up` / `make down` | start / stop Postgres | 1.1a |
| `make migrate` | apply Alembic migrations (the nine v1 tables, plus `hr_answer` from 1.2 and `document.mask_spans` from 1.4a) | 1.1a |
| `make up-all` | whole stack in Docker (postgres, api, worker, web) | 1.1a |
| `make api` | FastAPI with reload on :8000 | 1.1a |
| `make worker` | job worker | 1.1a |
| `make web` | Vite dev server on :5173 | 1.1a |
| `make check` | ruff, pyright, unit tests, web typecheck and lint | 0 |
| `make test` | unit tests | 0 |
| `make test-int` | integration tests (needs `make up`) | 1.1a |
| `make setup-missing [POSITION=<id>] [YES=1]` | enqueue position setup for positions that have posting text but no requirements and no setup job; lists only unless `YES=1`; `POSITION` takes an id or its first characters | 1.2 |
| `make eval VARIANT=A SPLIT=dev [LIMIT=n] [STAGES=extraction,verdicts] [DRY_RUN=1] [YES=1]` | eval harness: loads the golden set, prints a metrics table and writes `eval/results/<time>_<variant>_<split>.json` with `pipeline_version` (git commit, prompt versions, model). The default stage is `verdicts`, against a stub judge until 1.4b: no model calls. `STAGES=extraction,verdicts` adds the requirement extraction, one real call per golden posting (cached by the response cache). `DRY_RUN=1` prints the call count and the estimated cost and calls nothing. A run that would make more than 5 uncached model calls is refused until `YES=1`. From 1.4a, `STAGES=masking` measures the masking leak rate (email, phone, name) against `eval/golden/contacts.json` with no model call; `STAGES=parsing` runs the CV parsing prompt on a seeded subset of at most 18 dev-split CVs (seed 20261117, one real call each; `DRY_RUN=1` prints the CV ids, the coverage proof, the model, the prompt version and the estimated cost; dev split only; a 429 stops the run and reports how many CVs were parsed: at once for a daily quota, after the client's 4 retries for a per-minute one). `FALLBACK=openrouter` (or `--fallback openrouter`, or `LLM_FALLBACK=openrouter`) opts in to the OpenRouter fallback: after a Gemini daily quota the rest of the run goes to the free model, at 20 requests per minute and at most 50 real calls per UTC day (read from `GET /api/v1/key`, `free_model_daily_requests`, and counted locally in `LLM_CACHE_DIR`). A run that used it is labelled `dev-smoke, non-baseline` in its report and result file, with both model names; its numbers are not baselines. `DRY_RUN=1` prints the fallback line when it is on | 1.3 |
| `uv run python -m ats.eval build` | validate the golden set's profiles, write `labels/*.jsonl` and `split.json` (see `eval/golden/README.md`) | 1.3 |
| `uv run python -m ats.eval render` | render posting and CV sources to PDF; writes only the files whose bytes change | 1.3 |
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
| `UPLOAD_DIR` | `data/uploads` | stored PDFs, one file per `sha256`; in Docker the `uploads` volume at `/app/data/uploads` | 1.1b |
| `MAX_UPLOAD_MB` | `10` | largest accepted PDF; a bigger one gets HTTP 413 | 1.1b |
| `LLM_MODEL` | `gemini-3.6-flash` | model for every LLM role. The plan (§6.1) names `gemini-3.8-flash`, which returned 503 persistently; set it back when it is reachable. Eval results must name the model | 1.2 |
| `LLM_API_KEY` | none | Gemini API key; never committed | 1.2 |
| `LLM_RPM` | `5` | requests per minute (free tier). The limiter is in-process: valid for one worker only | 1.2 |
| `LLM_CACHE_DIR` | `data/llm_cache` | LLM response cache, one JSON file per hash of model, prompts, thinking level and schema; in Docker the `llm_cache` volume | 1.2 |
| `LLM_FALLBACK` | empty (off) | eval runs only: `openrouter` continues a run on an OpenRouter free model after a Gemini daily quota. The API and the worker never read it. Also `make eval FALLBACK=openrouter` | 1.4a |
| `OPENROUTER_API_KEY` | none | key for the fallback; never committed; needed only with `LLM_FALLBACK` | 1.4a |
| `OPENROUTER_MODEL` | `google/gemma-4-31b-it:free` | the free model the fallback uses (checked in OpenRouter's public model list on 2026-11-17) | 1.4a |
| `QUOTE_FUZZY_THRESHOLD` | `90` | a judge quote passes the quote check when it is in the CV verbatim after normalization, or at this `rapidfuzz` score (0 to 100) or above; numbers in the quote must exist verbatim either way (§3.2) | 1.4b |
| `GIT_COMMIT` | derived from `git` | overrides the code version in the worker's startup line; set it where there is no `.git` (a Docker image shows `unknown` otherwise) | 1.2 |
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
| 1.4a | `httpx` moved from the dev group to the main dependencies (the OpenRouter transport uses it). It was already in `uv.lock` through `google-genai`; the lock gained no package | |
| 1.3 | eval group: `scikit-learn` (brings `numpy`, `scipy`, `joblib`, `threadpoolctl`); `statsmodels` is deferred to 1.8 | |
| 1.4b | `rapidfuzz` (3.14.6; quote checking, §6.3; it was the only package `uv add` put in `uv.lock`) | |
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

`google-genai` (phase 1.2) is imported only in `src/ats/llm/gemini.py`, behind the `LLMClient`
interface. `gemini-3.8-flash` does not accept `thinking_level` `minimal` (it takes `low`, `medium`
and `high`; default `medium`), so every call uses `low` or higher, which also works on the
current default `gemini-3.6-flash`.

The `eval` group is a default group (`[tool.uv] default-groups` in `pyproject.toml`), so `uv run`
and `make check` see scikit-learn. The API and worker Dockerfiles sync with `--no-dev --no-group eval`:
neither runs an evaluation, and numpy and scipy would add weight to both images.

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
| 2026-11-16 | Docker volume `ats_uploads` (compose project `ats`) | uploaded PDFs shared by api and worker (phase 1.1b) | `docker compose --profile full down -v` (deletes the PDFs and the database) or `docker volume rm ats_uploads` |
| 2026-11-16 | Docker images `ats-api`, `ats-worker`, `ats-web`, plus base images `python:3.12-slim`, `node:24-alpine` and `ghcr.io/astral-sh/uv:0.13.8` | `make up-all` (phase 1.1a) | `docker compose --profile full down --rmi local`, then `docker rmi python:3.12-slim node:24-alpine ghcr.io/astral-sh/uv:0.13.8` |
| 2026-11-16 | Docker volume `ats_llm_cache` (compose project `ats`) | LLM response cache of the worker (phase 1.2) | `docker compose --profile full down -v` or `docker volume rm ats_llm_cache` |
