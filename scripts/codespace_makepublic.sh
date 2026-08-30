#!/usr/bin/env bash
# Auto-share port 8000 publicly on every create/start/rebuild.
# gh is preinstalled + pre-authed inside Codespaces. The tunnel/port may not be
# registered yet on a fresh start, so retry with logging instead of failing
# silently (a private port = 401 to anyone who hits the URL).
set -u
LOG=/tmp/makepublic.log
: > "$LOG"
echo "[$(date -u +%H:%M:%S)] CODESPACE_NAME=${CODESPACE_NAME:-<unset>}" >> "$LOG"

if [ -z "${CODESPACE_NAME:-}" ] || ! command -v gh >/dev/null 2>&1; then
  echo "[$(date -u +%H:%M:%S)] gh or CODESPACE_NAME missing - cannot set visibility" >> "$LOG"
  exit 1
fi

for i in $(seq 1 10); do
  if gh codespace ports visibility 8000:public --codespace "$CODESPACE_NAME" >>"$LOG" 2>&1; then
    echo "[$(date -u +%H:%M:%S)] port 8000 set public (attempt $i)" >> "$LOG"
    exit 0
  fi
  echo "[$(date -u +%H:%M:%S)] attempt $i failed, retrying in 10s" >> "$LOG"
  sleep 10
done

echo "[$(date -u +%H:%M:%S)] giving up after 10 attempts" >> "$LOG"
exit 1