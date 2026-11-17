FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first, so editing code does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-group eval --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-group eval

ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --system --no-create-home app && mkdir -p /app/data/uploads && chown app /app/data/uploads
USER app

EXPOSE 8000
CMD ["uvicorn", "ats.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
