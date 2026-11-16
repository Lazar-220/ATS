# Separate from the API image on purpose: from phase 2.1 only the worker carries the models.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --system --no-create-home app && mkdir -p /app/data/uploads /app/data/llm_cache \
    && chown app /app/data/uploads /app/data/llm_cache
USER app

# Exec form, no wrapper: Python must be PID 1 to receive SIGTERM from `docker stop`.
CMD ["python", "-m", "ats.worker"]
