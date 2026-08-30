#!/usr/bin/env bash
# Auto-start script for GitHub Codespaces: runs the backend LIVE against
# api.fortyguard.com with the real LLM chain (Groq -> OpenRouter).
set -e

cd "$(dirname "$0")/.."

# Seeded from GitHub Codespaces repo secrets (Settings -> Secrets and variables -> Codespaces).
export FORTYGUARD_LIVE="${FORTYGUARD_LIVE:-true}"
export LLM_PROVIDER="${LLM_PROVIDER:-groq}"
export AEGIS_SYNTH_LLM="${AEGIS_SYNTH_LLM:-false}"
export PYTHONPATH=backend

echo "FORTYGUARD_LIVE=$FORTYGUARD_LIVE  LLM_PROVIDER=$LLM_PROVIDER"
echo "Starting uvicorn on 0.0.0.0:8000 ..."
cd backend
exec uvicorn app.main:app --host 0.0.0.0 --port 8000