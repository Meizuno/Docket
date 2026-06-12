#!/usr/bin/env bash
# Boot an embedded Postgres, ensure the docket database exists, then run the
# API. Both run in one container — convenient for a self-contained image, not
# how you'd separate concerns in production.
set -euo pipefail

export PGDATA="${PGDATA:-/var/lib/postgresql/data}"
# Debian keeps the server binaries (initdb, pg_ctl, ...) off PATH.
PATH="$(ls -d /usr/lib/postgresql/*/bin | head -1):$PATH"
export PATH

# First boot: initialise the cluster and listen only on loopback.
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    initdb --username=postgres --auth=trust >/dev/null
    echo "listen_addresses='127.0.0.1'" >>"$PGDATA/postgresql.conf"
fi

pg_ctl -D "$PGDATA" -w -l "$PGDATA/server.log" start

# Create the application database on first boot (idempotent thereafter).
if ! psql -h 127.0.0.1 -U postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='docket'" 2>/dev/null | grep -q 1; then
    createdb -h 127.0.0.1 -U postgres docket
fi

# Run uvicorn in the background so we can forward shutdown signals to both it
# and Postgres — `exec` would replace this shell and skip Postgres cleanup.
uvicorn docket.api.main:app --host 0.0.0.0 --port 8000 &
uvicorn_pid=$!

shutdown() {
    kill -TERM "$uvicorn_pid" 2>/dev/null || true
    wait "$uvicorn_pid" 2>/dev/null || true
    pg_ctl -D "$PGDATA" -m fast stop || true
    exit 0
}
trap shutdown TERM INT

wait "$uvicorn_pid"
pg_ctl -D "$PGDATA" -m fast stop || true
