# ═══════════════════════════════════════════════════════════════════
#  MIRA Health App — Dockerfile (Multi-stage)
#  Stage 1: Build React → Stage 2: Python + gunicorn
#
#  docker-compose up --build
# ═══════════════════════════════════════════════════════════════════

# ── Stage 1: Build React ────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install --silent
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python production server ──────────────────────────────
FROM python:3.11-slim AS production

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend
COPY backend/ ./backend/

# Copy built React from Stage 1
COPY --from=frontend-builder /app/frontend/build ./frontend/build

# Pre-train the ML model
RUN python backend/train_model.py

# Create persistent data dir
RUN mkdir -p /data

EXPOSE 5000

ENV PORT=5000 \
    DATA_DIR=/data \
    JWT_SECRET=mira-health-platform-jwt-secret-key-2025-production-secure-64chars!!

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"

# --preload: app module loaded once in master before workers fork
# This ensures db.create_all() + seed_admin() run exactly once
CMD gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers 2 \
    --threads 2 \
    --timeout 120 \
    --preload \
    --access-logfile - \
    --error-logfile - \
    backend.app:app
