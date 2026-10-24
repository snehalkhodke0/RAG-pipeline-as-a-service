#!/bin/sh
set -e

echo "Running Alembic migrations..."
alembic upgrade head

PORT="${PORT:-8000}"
echo "Starting uvicorn on port ${PORT}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
