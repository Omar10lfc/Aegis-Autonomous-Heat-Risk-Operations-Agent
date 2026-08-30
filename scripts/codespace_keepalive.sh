#!/usr/bin/env bash
# Keep the codespace alive: hit our own health endpoint every 4 minutes so the
# forwarded port keeps seeing activity and GitHub's idle timer keeps resetting.
# Stops immediately if the backend is no longer listening (e.g. it was stopped).
set -euo pipefail

while true; do
  curl -fsS -o /dev/null http://localhost:8000/health || exit 0
  sleep 240
done