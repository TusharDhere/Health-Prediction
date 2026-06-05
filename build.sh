#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  MIRA — Render Build Script
#  Runs once at deploy time:
#    1. Install Python deps
#    2. Build React frontend
#    3. Train ML model (skipped if model.pkl already exists)
# ─────────────────────────────────────────────────────────────────
set -e

echo "▶ [1/3] Installing Python dependencies..."
pip install -r backend/requirements.txt

echo "▶ [2/3] Building React frontend..."
cd frontend
npm install
npm run build
cd ..

echo "▶ [3/3] Training ML model (if needed)..."
if [ ! -f backend/model.pkl ]; then
  python backend/train_model.py
else
  echo "   model.pkl already exists — skipping training."
fi

echo "✅ Build complete."
