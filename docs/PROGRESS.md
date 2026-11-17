# Progress

Read this at the start of every session. Update it at the end of every phase.

## Phase status

| Phase | Status | Merged | Notes |
| --- | --- | --- | --- |
| 0 Bootstrap | merged | 2026-11-16 | Built directly on `main` as the phase prompt says; no merge commit. Three commits. |
| 1.1a Skeleton | merged | 2026-11-16 | `--no-ff` merge of `phase/1.1a-skeleton`. Commit 606dd06 alone fails pyright; fixed by 65f5d37, left unsquashed on the owner's decision. |
| 1.1b Ingest | merged | 2026-11-16 | `--no-ff` merge of `phase/1.1b-ingest`, five feature commits and one docs commit. |
| 1.2 Requirements | merged | 2026-11-17 | `--no-ff` merge of `phase/1.2-requirements`: five feature commits, one fix, one test, docs. Merged with the `gemini-3.8-flash` smoke criterion open (owner-approved deviation); superseded on 2026-11-17 when the default moved to `gemini-3.6-flash`, where the smoke run passed. |
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
| 2026-11-16 | 1.2 | requirement extraction, one real call, `gemini-3.6-flash` via the `LLM_MODEL` override (default unchanged), `thinking_level` low, synthetic posting. Run by the owner, not by Claude. Result: "Java" and "3 years of experience in Java" came back as two requirements with `parent`=1; "a degree and 3 years" came back as two separate requirements. Latency, 795 input and 354 output tokens | n/a | 58.7 s | none set | requirements_v1 |

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
| 2026-11-16 | 1.2 | `LLMClient` result: output tokens include thinking tokens (billed as output); a cache hit reports 0 tokens; both calls of an invalid-output retry are counted; cache entries are written only after validation. 429 is retried up to 4 times (provider's `retryDelay` if given, else 2 s doubling, capped at 60 s). 5xx: 500, 503 and 504 are retried at most twice (owner decision after three 503s from `gemini-3.8-flash`), with 2 s doubling backoff times a random factor from 1 to 2, capped at 60 s, each attempt through the rate limiter and with a budget separate from the 429 one; other 4xx and 5xx fail at once. The queue's three attempts remain on top of that. Cost in USD is not computed here. | Phase prompt asks for tokens, latency and the cache flag; `assessment.cost_usd` is written in 1.4b. | Leaving 5xx to the queue alone |
| 2026-11-16 | 1.2 | The prompt version is logged with every call and is not stored in the database. | No v1 table has a place for it; 1.4b has `assessment.trace`. | A new column |
| 2026-11-16 | 1.2 | `@tanstack/react-table` 9.3.1 (API differs from v8: `useTable`, `tableFeatures`, `createColumnHelper`). The edit screen keeps one `dedup_key` per distinct request body, so a double click or a retry after a network error repeats the request instead of doing it twice. | Checked against the package's own getting-started guide. | v8 |
| 2026-11-16 | 1.2 | Phase 1.2 is merged with the `gemini-3.8-flash` smoke criterion still OPEN (see Carried over). CLAUDE.md says an unmet criterion blocks the phase; the owner approved this one deviation explicitly. | The model returned 503 three times; the same prompt and schema passed on `gemini-3.6-flash`, and the 5xx retry now exists. | Holding the phase until the model recovers |
| 2026-11-17 | 1.3 (config) | **Deviation from §6.1:** the default `LLM_MODEL` is `gemini-3.6-flash`, not `gemini-3.8-flash` (settings, `.env.example`, `compose.yaml`, SETUP.md). Every eval baseline must name the model it was measured on. Re-measure the baselines on `gemini-3.8-flash` when it is reachable, and compare before choosing the model for the v1 gate. | `gemini-3.8-flash` still returned 503 after the 5xx retry (4 minutes, 2 retries); `gemini-3.6-flash` passed the smoke run. Numbers measured on 3.6 are not evidence about 3.8 or the §6.1 cost estimate (which assumes 3.8 pricing). | Waiting for 3.8; raising the retry budget |
| 2026-11-17 | 1.3 | **Labelling conventions** for the golden set (written in `eval/golden/README.md`): a duration requirement is `partial` when the union of periods is at least 50% of `min_months`, `not_met` below that; "basic knowledge" wording, a skill that is only listed, and a degree in progress are `partial`; tenure is the union of overlapping periods; "present" means 2026-11-17; relevance 3/2/1/0 is a design judgement. The plan (§5.1) names the hard cases but not the verdicts they get. | These are mine, not the plan's. Phase 1.4a and 1.4b must compute tenure the same way, or the overlapping-periods case will fail for a reason that is not the judge's. | `partial` only for a skill in a list was weighed against `met` and `not_met`; none of the three is obviously right |
| 2026-11-17 | 1.3 | Golden profiles hold the verdict, the fact and the quote (one hand-written place); `labels/*.jsonl` and `split.json` are derived by `python -m ats.eval build`, and the loader refuses a set whose files differ from the profiles. A gold quote must sit inside one line of one column, because two-column CVs are extracted interleaved. Two-column sources are `left`, a `=== RIGHT COLUMN ===` line, then `right`. | One source of truth for about 800 verdicts; the interleaving owner decision from the phase plan. | Hand-writing the JSONL next to the profile |
| 2026-11-17 | 1.3 | **Reference layouts imitated in the mini set** (read from `eval/reference/`, style only; not committed, not test items): (a) dark-sidebar Canva style, English, label above value, slash-separated skills with a trailing slash: `be_01`, two-column; (b) grey-sidebar style, Serbian Latin, `\| `-separated place and date, soft-skill bullets: `pm_04`, two-column; (c) Europass-style label/value, Serbian Latin and Cyrillic, date at the start of the line, ` • ` bullets, spaces inside parentheses: `be_02`, `pm_02`; (d) Word-style single column, headings in capitals, contact block with date of birth and a wrapped LinkedIn URL, `Mother tongue(s) ... Other language(s)` line, Serbian terms inside English text: `be_03`, `be_04`, `pm_01`, `pm_03`. Terse noun-phrase wording instead of first-person bullets with metrics; noise sections (date of birth, gender, driving licence, soft-skill lists). **Not imitated yet:** the graphic pink pill-heading layout; sidebar text extracted as a block before the main column; dates detached from their entries beyond what the row-by-row interleaving gives; a Europass language grid; glued-together words; photo placeholders. The renderer draws plain text, so bold, colour and graphics are absent, and only the text layer is realistic. | The first drafts were polished and metric-heavy, which the reference CVs are not. | Rendering a block-wise sidebar-first order (owner chose row by row) |

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
| 1.2 | **SUPERSEDED (2026-11-17): smoke run on `gemini-3.8-flash`.** The default model is now `gemini-3.6-flash` (see Decisions, 2026-11-17), and the smoke run passed on it: owner-run, 58.7 s, then a worker run on 2026-11-17 of 3.3 s for 1044 in / 508 out tokens. `gemini-3.8-flash` still returned 503 after the 5xx retry (4 minutes, 2 retries). The 3.8 re-measurement is tracked in the next row. | closed |
| 1.3 | Re-measure the eval baselines (extraction F1 and later metrics) on `gemini-3.8-flash` once it is reachable, and compare with the `gemini-3.6-flash` rows. | v1 gate (1.8), or earlier if 3.8 recovers |
| 1.2 | The rate limiter is in-process: correct with one worker. A second worker needs a shared limiter (a Postgres row or advisory lock). | when a second worker is added |
| 1.2 | Positions created before 1.2 have no setup job, so they stay `pending`. Only the development database has any; re-upload does not help because their documents are already extracted. | none (development data) |
