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

# --- runtime stage: app + embedded Postgres in one image -------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PGDATA=/var/lib/postgresql/data \
    DOCKET_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:5432/docket

# Postgres server + client live in the same image as the API.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p "$PGDATA" \
    && chown -R postgres:postgres "$PGDATA"

WORKDIR /app
# The `postgres` user is created by the postgresql package; the cluster cannot
# be initialised or run as root.
USER postgres

EXPOSE 8000

# /health pings the database, so a green check means both processes are up.
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
