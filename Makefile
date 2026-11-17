# Stable command contract; see docs/SETUP.md section 3.
UNIT_TESTS := not integration and not llm

.PHONY: check test \
	up down up-all migrate api worker web test-int setup-missing \
	eval \
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
# requirement extraction, which calls the model; DRY_RUN=1 prints calls and cost and calls nothing;
# YES=1 confirms a run of more than 5 model calls.
VARIANT ?= A
SPLIT ?= dev
eval:
	uv run python -m ats.eval run --variant $(VARIANT) --split $(SPLIT) 		$(if $(LIMIT),--limit $(LIMIT)) $(if $(STAGES),--stages $(STAGES)) 		$(if $(DRY_RUN),--dry-run) $(if $(YES),--yes) $(if $(FALLBACK),--fallback $(FALLBACK))

test-int:
	uv run pytest -q -m integration

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run pyright
	uv run pytest -q -m "$(UNIT_TESTS)"
	@if [ -d web ]; then npm --prefix web run typecheck && npm --prefix web run lint; \
	else echo "web/ not present yet (added in phase 1.1a): skipping frontend checks"; fi

test:
	uv run pytest -q -m "$(UNIT_TESTS)"

# Targets that belong to a later phase fail loudly instead of doing nothing.
langfuse-up langfuse-down: ; @echo "make $@ is added in phase 1.6"; exit 1
eval-redteam: ; @echo "make $@ is added in phase 1.7"; exit 1
reindex: ; @echo "make $@ is added in phase 2.1"; exit 1
mcp: ; @echo "make $@ is added in phase 3.7"; exit 1
