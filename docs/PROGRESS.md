# Progress

Read this at the start of every session. Update it at the end of every phase.

## Phase status

| Phase | Status | Merged | Notes |
| --- | --- | --- | --- |
| 0 Bootstrap | merged | 2026-11-16 | Built directly on `main` as the phase prompt says; no merge commit. Three commits. |
| 1.1a Skeleton | merged | 2026-11-16 | `--no-ff` merge of `phase/1.1a-skeleton`. Commit 606dd06 alone fails pyright; fixed by 65f5d37, left unsquashed on the owner's decision. |
| 1.1b Ingest | not started | | |
| 1.2 Requirements | not started | | |
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

## Carried over

Work a phase deferred, with the phase that must pick it up.

| From phase | Item | Picked up in |
| --- | --- | --- |
| 1.1a | Re-uploading a document whose status is `failed` must re-enqueue its ingest job, not silently return the existing row (owner correction). Note the table-wide unique `dedup_key`: the ingest key needs the attempt or a version, or the old finished job blocks the new one. | 1.1b |
| 1.1a | A real SIGINT/SIGTERM test of the worker on native Windows is not automated (kill and restart is; SIGTERM was verified in the Linux container). | 1.7 (CI on Linux) |
