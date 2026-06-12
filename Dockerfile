# syntax=docker/dockerfile:1

# --- build stage: install the app into an isolated venv ---------------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Only runtime artifacts (the venv) cross into the final image.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
# README.md is referenced by pyproject's `readme` field, so the build needs it.
COPY pyproject.toml README.md ./
COPY docket ./docket
RUN pip install .

# --- runtime stage: slim image, non-root, just the venv --------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Run unprivileged; nothing in the app needs root.
RUN useradd --create-home --uid 10001 appuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# Migration tooling: `alembic upgrade head` is run by the compose migrate step.
COPY alembic.ini ./
COPY alembic ./alembic
USER appuser

EXPOSE 8000

# /health pings the database; a green check means the API can serve.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "docket.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
