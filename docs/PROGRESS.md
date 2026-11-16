# Progress

Read this at the start of every session. Update it at the end of every phase.

## Phase status

| Phase | Status | Merged | Notes |
| --- | --- | --- | --- |
| 0 Bootstrap | merged | 2026-11-16 | Built directly on `main` as the phase prompt says; no merge commit. Three commits. |
| 1.1a Skeleton | merged | 2026-11-16 | `--no-ff` merge of `phase/1.1a-skeleton`. Commit 606dd06 alone fails pyright; fixed by 65f5d37, left unsquashed on the owner's decision. |
| 1.1b Ingest | merged | 2026-11-16 | `--no-ff` merge of `phase/1.1b-ingest`, five feature commits and one docs commit. |
| 1.2 Requirements | built, not merged | | All units done. The manual smoke run against Gemini is NOT done: three attempts on 2026-11-16 got HTTP 503 (model overloaded). Run `uv run pytest -m llm -s tests/test_llm_smoke.py` and record the output here. |
| 1.3 Golden set and harness | not started | | |
| 1.4a CV parsing | not started | | |
| 1.4b Judge and score | not started | | |
| 1.5 Interface | not started | | |
| 1.6 Observability | not started | | |
| 1.7 Guardrails and CI | not started | | |
| 1.8 v1 gate | not started | | |
| 2.1 Chunking and embeddings | not started | | |
| 2.2 Evidence retrieval | not started | | |
| 2.3 Endpoint 2 | not started | | |
| 2.4 Batch | not started | | |
| 2.5 HNSW experiment | not started | | |
| 2.6 v2 gate and refactor | not started | | |
| 3.1 Code validator | not started | | |
| 3.2 Verifier and re-judging | not started | | |
| 3.3 Questions and rules | not started | | |
| 3.4 Resolver | not started | | |
| 3.5 Rubric lint and question value | not started | | |
| 3.6 LangGraph port | not started | | |
| 3.7 MCP and notifications | not started | | |
| 3.8 Red-team | not started | | |

## Measured numbers

One row per measurement. Never overwrite a row; add a new one.

| Date | Phase | Metric | Split | Value | Target | pipeline_version |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-16 | 1.1a | docker stats memory, `postgres` (idle, `shared_buffers` 512 MB) | n/a | 70 MiB | about 1 GB (§6.3) | n/a |
| 2026-11-16 | 1.1a | docker stats memory, `api` (idle, no models) | n/a | 47 MiB | about 0.3 GB (§6.3) | n/a |
| 2026-11-16 | 1.1a | docker stats memory, `worker` (idle, no models yet) | n/a | 33 MiB | about 2.5 GB with bge-m3 (§6.3) | n/a |
| 2026-11-16 | 1.1a | docker stats memory, `web` (Vite dev server, idle) | n/a | 253 MiB | about 0.5 GB (§6.3) | n/a |
| 2026-11-16 | 1.1b | docker stats memory, `worker` after ingesting a PDF (PyMuPDF and lingua loaded, sr/hr/bs/en models) | n/a | 71 MiB | about 2.5 GB with bge-m3 (§6.3) | n/a |
| 2026-11-16 | 1.1b | docker stats memory, `api` after serving uploads (no PyMuPDF, no lingua) | n/a | 55 MiB | about 0.3 GB (§6.3) | n/a |

## Decisions

One entry per decision that the plan left open or that deviates from it.

| Date | Phase | Decision | Why | Alternatives rejected |
| --- | --- | --- | --- | --- |
| 2026-11-16 | 1.1a | `docs/schema.sql` does not exist, so the v1 DDL was derived from §2.5 and approved by the owner before the migration. `request_candidate` is keyed by `document_id` with a nullable `candidate_id`. `verdict` is one row per (assessment, requirement) until v2. | A candidate exists only after CV parsing (1.4a), but request rows are created at upload (1.1b). v2 adds `iteration` / `is_current` (§7). | Keying on `candidate_id`; append-only verdicts in v1 |
| 2026-11-16 | 1.1a | `assessment.status` has no CHECK; `verdict.verdict` and `requirement.kind` do (kind is NOT NULL). Requirement edits insert new rows under the new `rubric_version` and keep old ones. Cascades only from position, assessment and request; `verdict.requirement_id` has none. | Owner correction. v2 brings a 7-state machine; v3 extends `verdict` with `pending_hr`. | CHECK on `assessment.status` |
| 2026-11-16 | 1.1a | `verdict.requirement_id` foreign key is `DEFERRABLE INITIALLY DEFERRED`. | Without it, deleting a position fails: the cascade into `requirement` is checked before the cascade into `assessment` and `verdict` finishes. Deleting a still-referenced requirement alone still fails at commit. | Immediate check (breaks position deletion); `ON DELETE CASCADE` (violates the owner correction) |
| 2026-11-16 | 1.1a | A job requeued after the visibility timeout keeps its `attempts`, so it counts toward the three. `task_queue.dedup_key` is unique over the whole table, finished jobs included. `complete` and `fail` only act on the attempt that claimed the job. | A job that crashes its worker must not loop forever; a slow worker must not overwrite a job already handed to another. Callers put a version in the key for deliberate re-runs. | Resetting attempts on requeue; unique only among live jobs |
| 2026-11-16 | 1.1a | `web/` pins `typescript-eslint` to 8.72.0 and carries `@emnapi/core` and `@emnapi/runtime` as dev dependencies; the web image uses `node:24-alpine`. | Registry 404 on the 8.73.0 tarball; an npm lockfile bug breaks `npm ci` on Linux. See SETUP.md section 5. | Plain `npm install` in the image (not reproducible) |
| 2026-11-16 | 1.1a | The worker image is separate from the API image. | From 2.1 only the worker carries the models (§6.3). | One shared Python image |
| 2026-11-16 | 1.1b | Request status is derived at read time from the document statuses, not stored: `queued` (no document picked up), `running` (some still `uploaded`), `done` (none left), `failed` (the posting is `rejected` or `failed`). `ranking_request.status` stays `queued` until a later phase has a stage after ingest. | Owner decision. Storing it needs coordination between the independent ingest jobs, and 1.4b replaces it with real stages anyway. Two refinements beyond the first proposal: the `queued` state, and `failed` for a rejected posting (nothing to score against). | Stored status updated by the handler |
| 2026-11-16 | 1.1b | Job handlers take `(Job, ConnectionPool)` instead of `(Job)`. | A handler needs its own short transactions. Touched `registry.py`, `loop.py`, `noop` and one worker test. | Module-global pool |
| 2026-11-16 | 1.1b | `pymupdf` is pinned `>=1.28,<2`. | 2.x is a meta-package that also installs `pymupdf-layout`, `pymupdf4llm`, `onnxruntime`, `numpy`, `networkx`: weight 1.1b does not use. Revisit in 1.4a if structured extraction wants them. | PyMuPDF 2.x |
| 2026-11-16 | 1.1b | `document.lang` is `sr` (Serbian, Croatian and Bosnian as one class), `en` or `unknown`; `script` is `latin`, `cyrillic`, `mixed` or `unknown`. A text is `mixed` when the minority script is at least 10% of its letters. Scan threshold is 100 non-space characters per page on average (`MIN_CHARS_PER_PAGE`); upload cap 10 MB (`MAX_UPLOAD_MB`). | Owner approved the defaults. Lingua labels Serbian Latin as Bosnian (0.78) or Croatian (0.22) and Serbian Cyrillic as Serbian (1.0); the three confidences are summed per class. | Storing the detector's own label |
| 2026-11-16 | 1.1b | `document.storage_path` holds the file name relative to `UPLOAD_DIR` (`<sha256>.pdf`). In Compose the `uploads` volume is mounted at `/app/data/uploads` in api and worker. | API and worker may mount the directory at different paths. | Absolute paths |
| 2026-11-16 | 1.1b | Re-uploading a `failed` document flips it to `uploaded` and enqueues with a fresh dedup key (`ingest:<id>:<uuid>`); a `rejected` one is left alone. The handler marks a document `failed` on the last queue attempt, and skips any document that is no longer `uploaded`. The same bytes uploaded as posting and as CV (in one call or across calls) get HTTP 422. Documents are registered in `sha256` order so concurrent uploads sharing CVs cannot deadlock. | Closes the 1.1a carry-over. A rejection is deterministic, so retrying it is pointless; the skip makes a redelivered job harmless. | Resetting attempts; one shared document for both kinds |
| 2026-11-16 | 1.1b | `document.flags` is not written in 1.1b. | Nothing in this phase produces a flag; hidden-text flags arrive in 1.7. | Inventing flags (for example for unknown language) |
| 2026-11-16 | 1.2 | Requirement extraction uses `thinking_level` `low`, not `minimal` (§6.1, phase prompt). `thinking_level` is still a per-call parameter. | Google's thinking docs and release notes: `gemini-3.8-flash` accepts low, medium, high (default medium) and rejects `minimal`. | `medium`; switching `LLM_MODEL` to `gemini-3.6-flash` (supports `minimal`) |
| 2026-11-16 | 1.2 | `position_setup` is enqueued by the ingest handler, in the transaction that stores the posting text, not by endpoint 1. Dedup key `position_setup:<position_id>`. Uploading the same posting again resets a `failed` setup job (same row, attempts back to 0) so "upload again to retry" is true. | The text does not exist when endpoint 1 returns; a rejected scan would waste a job. A posting is ingested once per `sha256`, so an existing position skips setup. | Enqueue from endpoint 1 (needs a race with ingest) |
| 2026-11-16 | 1.2 | Migration 0002 adds `hr_answer` (`dedup_key` primary key, `position_id`, `type`, `request_sha256`, `rubric_version`, `rejudge_jobs`). A repeat returns the stored result with `duplicate: true`; the same key with a different request or position is 409; an answer for a version that is no longer current is 409. | An edit on a position with no assessments enqueues no jobs, so `task_queue` cannot dedup it. `request_sha256` and `rejudge_jobs` are additions to the approved columns, so a replay returns the original result. | `dedup_key` column on `job_position` |
| 2026-11-16 | 1.2 | An edit leaves `rubric_status` unchanged; only Confirm sets `confirmed`. | Owner decision. | Reset to unconfirmed; set to confirmed |
| 2026-11-16 | 1.2 | `id` and `parent` in a requirement list are labels inside that list, not database keys; the same shape is the extraction schema and the edit payload. Weight is an integer 1 to 5 (default 1). The extraction does not return a title: positions are listed by the posting's file name. | A list is stored as new rows, so the labels only say which row refines which. Weight scale and the missing title are mine; the golden set (1.3) shows whether the weights are useful. | Database ids in the payload; a title in the extraction |
| 2026-11-16 | 1.2 | `LLMClient` result: output tokens include thinking tokens (billed as output); a cache hit reports 0 tokens; both calls of an invalid-output retry are counted; cache entries are written only after validation. 429 is retried up to 4 times (provider's `retryDelay` if given, else 2 s doubling, capped at 60 s). 5xx is not retried by the client; the queue's three attempts cover it. Cost in USD is not computed here. | Phase prompt asks for tokens, latency and the cache flag; `assessment.cost_usd` is written in 1.4b. | Retrying 5xx in the client |
| 2026-11-16 | 1.2 | The prompt version is logged with every call and is not stored in the database. | No v1 table has a place for it; 1.4b has `assessment.trace`. | A new column |
| 2026-11-16 | 1.2 | `@tanstack/react-table` 9.3.1 (API differs from v8: `useTable`, `tableFeatures`, `createColumnHelper`). The edit screen keeps one `dedup_key` per distinct request body, so a double click or a retry after a network error repeats the request instead of doing it twice. | Checked against the package's own getting-started guide. | v8 |

## Carried over

Work a phase deferred, with the phase that must pick it up.

| From phase | Item | Picked up in |
| --- | --- | --- |
| 1.1b | Two-column layouts extract interleaved, row by row: left cell, right cell, next row (fixture in `tests/test_extract.py`: "Work experience, Skills, 2019-2023 Project Manager, Python SQL, ..."). Reading order is not reconstructed in 1.1b. | 1.4a (structured extraction, §2.2) |
| 1.1b | `document.flags` is empty; hidden-text and invisible-Unicode cleaning plug in as extra cleaning steps in `pipeline/extract.py`. | 1.7 |
| 1.1b | Rejected scans stay rejected; OCR is not attempted. | after v3 |
| 1.1a | A real SIGINT/SIGTERM test of the worker on native Windows is not automated (kill and restart is; SIGTERM was verified in the Linux container). | 1.7 (CI on Linux) |
| 1.2 | Extraction F1 of at least 0.85 on the golden postings. | 1.3 (golden set) |
| 1.2 | "Editing requirements re-scores that position's CVs": the edit enqueues one `rejudge` job per assessment, but no handler exists, and no assessment exists before 1.4b. | 1.4b (judge) |
| 1.2 | Manual smoke run against Gemini: not done, three HTTP 503 responses (model overloaded). | 1.2, before merge |
| 1.2 | The rate limiter is in-process: correct with one worker. A second worker needs a shared limiter (a Postgres row or advisory lock). | when a second worker is added |
| 1.2 | Positions created before 1.2 have no setup job, so they stay `pending`. Only the development database has any; re-upload does not help because their documents are already extracted. | none (development data) |
| 1.2 | Whether the client should retry 5xx (503 overloaded) itself, or leave it to the queue. | owner decision |
