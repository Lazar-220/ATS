# Stable command contract; see docs/SETUP.md section 3.
UNIT_TESTS := not integration and not llm

.PHONY: check test \
	up down up-all migrate api worker web test-int setup-missing \
	eval smoke-real api-types \
	langfuse-up langfuse-down \
	eval-redteam \
	reindex \
	mcp

up:
	docker compose up -d --wait postgres

up-all:
	docker compose --profile full up -d --build --wait

down:
	docker compose --profile full down

migrate:
	uv run alembic upgrade head

worker:
	uv run python -m ats.worker

web:
	npm --prefix web run dev

api:
	uv run uvicorn ats.api.main:app --reload --port 8000

# Enqueue position setup for positions that never got a job. Lists only, unless YES=1.
# Optional POSITION=<id or its first characters>. The worker makes the LLM calls.
setup-missing:
	uv run python -m ats.worker.setup_missing $(if $(POSITION),--position $(POSITION)) $(if $(YES),--yes)

# Evaluation harness. make eval VARIANT=A SPLIT=dev LIMIT=5. STAGES=extraction,verdicts adds the
# requirement extraction, which calls the model; STAGES=judge is the variant A judge (a parse and
# a judge call per CV of SPLIT); DRY_RUN=1 prints calls and cost and calls nothing; YES=1 confirms a
# run of more than 5 model calls.
VARIANT ?= A
SPLIT ?= dev
eval:
	uv run python -m ats.eval run --variant $(VARIANT) --split $(SPLIT) 		$(if $(LIMIT),--limit $(LIMIT)) $(if $(STAGES),--stages $(STAGES)) 		$(if $(DRY_RUN),--dry-run) $(if $(YES),--yes) $(if $(FALLBACK),--fallback $(FALLBACK))

# Manual real-model smoke test: the variant A judge on 2 dev CVs (4 calls, a few cents). Dry run
# unless YES=1. Honours LLM_MODEL and LLM_RPM. Needs LLM_API_KEY; never run by make check.
smoke-real:
	uv run python -m ats.eval run --variant A --split dev --limit 2 --stages judge --require-real $(if $(YES),--yes,--dry-run)

# Langfuse self-host (six services, about 4 GB of RAM; run `make down` first, see docs/SETUP.md).
# The UI is on http://localhost:3000. Stopping keeps the traces (no -v).
langfuse-up:
	docker compose -f compose.langfuse.yaml up -d --wait

langfuse-down:
	docker compose -f compose.langfuse.yaml down

# Regenerate the web types from the API schema (no server or database needed).
api-types:
	uv run python -m ats.api.openapi
	npm --prefix web run gen:types

test-int:
	uv run pytest -q -m integration

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run pyright
	uv run pytest -q -m "$(UNIT_TESTS)"
	@if [ -d web ]; then npm --prefix web run check:types && npm --prefix web run typecheck && npm --prefix web run lint && npm --prefix web run test; \
	else echo "web/ not present yet (added in phase 1.1a): skipping frontend checks"; fi

test:
	uv run pytest -q -m "$(UNIT_TESTS)"

# Red-team set (phase 1.7): 20 pairs of a clean golden CV and the same CV with an attack. No model
# is called: the metric is the share of attacks that change the judge input. JUDGE=1 (or YES=1) also
# judges the pairs whose input changed with the real model (about 12 calls); DRY_RUN=1 prints the
# count, YES=1 confirms. Needs LLM_API_KEY; refuses LLM_PROVIDER=fake.
eval-redteam:
	uv run python -m ats.eval redteam $(if $(or $(JUDGE),$(YES)),--judge) $(if $(DRY_RUN),--dry-run) $(if $(YES),--yes)

# CI smoke eval (phase 1.7): 20 synthetic golden CVs answered from the committed cache in
# eval/smoke_cache/, never from a model; exits non-zero on a cache miss or when accuracy or quote
# validity falls below the thresholds in the cache's manifest. Needs no key and no network.
smoke:
	uv run python -m ats.eval smoke

# Rebuild eval/smoke_cache. Default: the demo provider (no key, no cost; the manifest says DEMO,
# non-baseline). REAL=1 records the configured model instead (about 40 calls): DRY_RUN=1 prints
# the count, YES=1 confirms. Rebuild after any change to a prompt, the fence, extraction or masking:
# those change the cache keys and the smoke then fails with "rebuild".
smoke-cache:
	uv run python -m ats.eval smoke-cache $(if $(REAL),--real) $(if $(DRY_RUN),--dry-run) $(if $(YES),--yes)

# What .github/workflows/ci.yml runs, in one command. Needs `make up` (Postgres) for test-int.
ci: check test-int smoke

# Targets that belong to a later phase fail loudly instead of doing nothing.
reindex: ; @echo "make $@ is added in phase 2.1"; exit 1
mcp: ; @echo "make $@ is added in phase 3.7"; exit 1
