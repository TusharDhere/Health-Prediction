# ═══════════════════════════════════════════════════════════════════
#  MIRA Health App — Dockerfile
#  Stage 1 (node) → Build React
#  Stage 2 (python) → Production Flask + gunicorn
# ═══════════════════════════════════════════════════════════════════

FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install --silent
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS production
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/build ./frontend/build

RUN python backend/train_model.py
RUN mkdir -p /data

EXPOSE 5000

ENV PORT=5000 \
    DATA_DIR=/data \
    JWT_SECRET=mira-health-platform-jwt-secret-key-2025-production-secure-64chars!!

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"

CMD gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers 2 \
    --threads 2 \
    --timeout 120 \
    --preload \
    --access-logfile - \
    --error-logfile - \
    backend.app:app
