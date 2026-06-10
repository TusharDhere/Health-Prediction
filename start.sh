#!/usr/bin/env bash
set -e

PORT="${PORT:-5000}"
DATA_DIR="${DATA_DIR:-/data}"

echo "🚀 Starting MIRA on port $PORT  |  DB → $DATA_DIR/mira.db"
export DATA_DIR="$DATA_DIR"

exec gunicorn \
  --bind "0.0.0.0:$PORT" \
  --workers 2 \
  --threads 2 \
  --timeout 120 \
  --preload \
  --access-logfile - \
  --error-logfile - \
  backend.app:app
