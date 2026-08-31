"""Vercel Python Serverless entrypoint for Aegis FastAPI backend."""
import os
import sys
import traceback
from pathlib import Path

# ── Path setup: add backend/ to sys.path so `from app.*` imports work ──
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# ── Coerce empty-string env vars that Vercel injects ──
for key in list(os.environ):
    if os.environ[key] == "" and key.startswith(("FORTYGUARD_", "AEGIS_", "LANGCHAIN_", "LANGSMITH_")):
        del os.environ[key]

os.environ.setdefault("FORTYGUARD_LIVE", "false")
os.environ.setdefault("AEGIS_SYNTH_LLM", "false")

try:
    from app.main import app  # noqa: F401 — Vercel detects this ASGI app
except Exception:
    # If the real app fails to import, serve a diagnostic FastAPI app
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI()

    _tb = traceback.format_exc()

    @app.get("/{path:path}")
    @app.post("/{path:path}")
    async def _diagnostic(path: str):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Aegis backend failed to start",
                "traceback": _tb,
                "sys_path": sys.path[:5],
                "backend_dir_exists": BACKEND_DIR.exists(),
                "backend_contents": [
                    str(p.relative_to(BACKEND_DIR))
                    for p in BACKEND_DIR.rglob("*.py")
                ][:20] if BACKEND_DIR.exists() else [],
            },
        )
