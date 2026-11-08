#!/usr/bin/env bash
# Starts the FastAPI backend (port 8000) and the Streamlit UI (port 8501) for local development.
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
[ -f .env ] && { set -a; . ./.env; set +a; }   # STAFF_PIN, keys etc. for both processes
(cd backend && uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null' EXIT
(cd frontend && BACKEND_URL=http://localhost:8000 streamlit run app.py)
