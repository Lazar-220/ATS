# Stable command contract; see docs/SETUP.md section 3.
UNIT_TESTS := not integration and not llm

.PHONY: check test \
	up down up-all migrate api worker web test-int \
	eval \
	langfuse-up langfuse-down \
	eval-redteam \
	reindex \
	mcp

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
up down up-all migrate api worker web test-int: ; @echo "make $@ is added in phase 1.1a"; exit 1
eval: ; @echo "make $@ is added in phase 1.3"; exit 1
langfuse-up langfuse-down: ; @echo "make $@ is added in phase 1.6"; exit 1
eval-redteam: ; @echo "make $@ is added in phase 1.7"; exit 1
reindex: ; @echo "make $@ is added in phase 2.1"; exit 1
mcp: ; @echo "make $@ is added in phase 3.7"; exit 1
