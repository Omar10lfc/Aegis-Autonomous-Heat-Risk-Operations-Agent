#!/usr/bin/env bash
# Auto-share port 8000 publicly on every create/start/rebuild.
# GitHub does not honour "visibility" in portsAttributes, so we re-apply it
# via the GitHub CLI (preinstalled + pre-authed inside Codespaces) each start.
set -u

if [ -n "${CODESPACE_NAME:-}" ] && command -v gh >/dev/null 2>&1; then
  gh codespace ports visibility 8000:public --codespace "$CODESPACE_NAME" >/dev/null 2>&1 || true
fi
exit 0