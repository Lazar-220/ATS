# ATS tool: project guide

A CV-ranking service: HR uploads a job posting PDF and CV PDFs, the system scores every CV
against the posting's requirements and shows a ranked list with a verdict and a verbatim
quote per requirement. Built in three gated versions (v1 judge, v2 retrieval, v3 agent loop).

## Where things are

| File | Role |
| --- | --- |
| `docs/plan.md` | Source of truth for architecture and scope. Cite sections as §2.4, §3.2, etc. |
| `docs/prompts/` | One prompt per phase. Work on exactly one phase per session. |
| `docs/PROGRESS.md` | Phase status, measured numbers, decisions. Read it at the start of every session. |
| `docs/SETUP.md` | Prerequisites, dependencies, env vars, run commands. Keep it current. |
| `docs/schema.sql` | Full DDL, if present. When present it overrides anything you would derive from §2.5. |

Do not load all of `docs/plan.md` every session. Read the sections the phase prompt names.

## How to work on a phase

1. Read the phase prompt, `docs/PROGRESS.md`, the plan sections the prompt names, and the code you will touch.
2. Present a short plan: files, commit units, open questions. Wait for approval before editing.
3. Create branch `phase/<id>-<slug>` from `main`.
4. Build one commit unit at a time. Verify it, then commit it. Do not batch units into one commit.
5. When every "Done when" item has evidence (a command and its output, a test, a measured number),
   update `docs/PROGRESS.md` and `docs/SETUP.md`, then write the phase report (format below).
6. Merge into `main` with `--no-ff` only after the owner confirms the report.

If a "Done when" item cannot be met, stop and say so. Do not weaken the criterion, skip a test,
or move on to the next phase. If the plan and the code disagree, or the plan is ambiguous,
propose options and ask; record the decision in `docs/PROGRESS.md`.

Build only what the current phase asks for. v2 and v3 features wait for their gates (§7),
even when adding them now looks cheap.

## Architecture invariants

These hold in every phase. A change that breaks one needs the owner's explicit approval.

- **Code computes, the LLM judges.** Scores, tenure, date arithmetic and rankings are computed by code (§2.4, §2.2).
- **Every LLM output is a Pydantic schema.** Invalid output gets one retry call, then the job is `failed` (§4.5).
- **All LLM calls go through `LLMClient`**: rate limiting, retry on 429, response cache keyed by the hash
  of model, prompt and parameters, token and cost accounting. Model and key come from `LLM_MODEL` and
  `LLM_API_KEY`. No LangChain in v1 or v2 (§6.1, §6.3).
- **The LLM receives only masked text.** Name, email, phone and address live only in the `candidate` table (§2.4).
- **CV text is untrusted data.** It goes into a fenced data block; the system message says the block is inert.
  The judge has no tools. Text from a CV never becomes a rule and never reaches HR as an instruction (§4.4).
- **Grounding.** A `met` or `partial` verdict carries a verbatim quote, and code checks that the quote exists in the CV (§3.2).
- **Models live in the worker.** The embedding model and the reranker are loaded only in the worker process,
  never in the API process (§6.3).
- **The job queue is the `task_queue` table** with `FOR UPDATE SKIP LOCKED`. No Redis, no Celery (§2.5).
- **Raw SQL through psycopg 3.** Alembic for migrations. No ORM for queries.
- **Idempotency everywhere.** `sha256` for documents and positions, one assessment per candidate–position pair,
  `dedup_key` on jobs. A repeated request or a restarted worker must not create duplicates or pay for the same LLM call twice.
- **Embeddings over original text, lexical search over normalized text** (§2.2).
- **Prompt order for caching:** stable prefix first (instructions, rubric, rules), the CV last (§4.5).

## Testing and the LLM quota

- Tests never call the real LLM. Use the fake `LLMClient`. The free Gemini quota is about 20 requests per day (§6.1).
- Pytest markers: `integration` (needs Postgres running), `llm` (calls the real model; never run automatically).
- Before any run that calls the real LLM more than 5 times, print the number of calls and the estimated cost,
  then wait for confirmation.
- Only synthetic CVs go to the free tier. Never read anything under `data/real/`.

## Command contract

`make` targets are the stable interface; keep them working and documented in `docs/SETUP.md`.

| Command | Does |
| --- | --- |
| `make up` / `make down` | start / stop Postgres in Docker |
| `make migrate` | apply Alembic migrations |
| `make api` | FastAPI with reload on :8000 |
| `make worker` | job worker |
| `make web` | Vite dev server on :5173 |
| `make check` | ruff, pyright, unit tests, web typecheck and lint |
| `make test` / `make test-int` | unit tests / integration tests |
| `make eval VARIANT=A` | eval harness (from phase 1.3) |

## Code conventions

- Python 3.12+, managed with `uv`. `src/ats/` layout: `api/`, `worker/`, `pipeline/`, `llm/`, `db/`, `services/`, `eval/`.
- Full type hints; pyright must pass. Pydantic v2 models at every boundary.
- Prompts are versioned files under `src/ats/prompts/`, never inline strings. Record the prompt version with every LLM call.
- Configuration through `pydantic-settings` and `.env`. Every new variable is added to `.env.example` and `docs/SETUP.md`.
- Frontend: React, TypeScript strict, Vite, TanStack Query and Table. Render CV text as text, never as HTML.
- Comments explain why, not what. No dead code, no speculative abstractions.

## Commits

- Conventional Commits: `feat(scope): …`, `fix`, `refactor`, `test`, `docs`, `chore`. Imperative, under 72 characters.
- One commit per commit unit from the phase prompt. Each commit leaves `make check` green.
- Never commit `.env`, anything under `data/`, model weights, or real CVs.
- Do not push, rewrite history, or merge into `main` without being asked.

## Dependencies

- Before adding a package, say which one and why. Prefer the standard library and packages the plan already names (§6.3).
- Add with `uv add` (or `uv add --group dev|eval`) and `npm install` inside `web/`. Commit lock files.
- Verify the current API of fast-moving SDKs against their documentation before writing code against them:
  `google-genai`, `langfuse`, `langgraph`, `mcp`, `sentence-transformers`. Do not rely on memory for signatures.
- Record every new dependency in `docs/SETUP.md` and in the phase report.

## Working outside the repository

The owner has explicitly authorized work outside this directory when the application needs it.
Allowed without asking for anything beyond the normal permission prompt:

- Docker images, containers, volumes and networks for this project (Postgres, Langfuse, n8n).
- Developer tooling through `uv`, `npm` or `pipx`.
- Model weights in the Hugging Face cache.
- Reading system configuration and logs to diagnose a problem.

Rules:

- Say what you are about to do outside the repository and why, before doing it.
- Prefer a project-local or Docker solution over a host-level install.
- Log every change outside the repository in `docs/SETUP.md` under "Machine state", with the command that undoes it.
- Ask first before: `sudo` or system package installs, deleting or overwriting anything outside the repository,
  editing shell profiles or global git configuration, touching containers or volumes that do not belong to this project.
- Never read credentials or personal files (`~/.ssh`, browser data, other projects' `.env` files).
- The machine has 12 GB of RAM. Check `docker stats` before starting another heavy service (§6.3 RAM budget).

## Phase report

End every phase with this, in the conversation:

```
## Phase <id> report
**Built:** 3–6 bullets
**Commits:** <hash> <subject>, one per line
**New dependencies:** package, group, why. "None" if none.
**How to run and verify:** exact commands, in order
**Done when:** each criterion, with its evidence, or NOT MET and why
**Deviations from the plan:** what and why. "None" if none.
**Open questions:** for the owner
```
