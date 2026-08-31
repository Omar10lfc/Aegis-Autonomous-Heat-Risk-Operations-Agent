from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agent.graph import configure_langsmith
from app.api.routes import router
from app.config import get_settings

settings = get_settings()
configure_langsmith(settings)

app = FastAPI(
    title="Aegis",
    description="Goal-driven heat-risk agent for FortyGuard Hackathon'26 (Agentic Track).",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Mount API Router & Endpoints FIRST (both root and /api prefix)
app.include_router(router)
app.include_router(router, prefix="/api")


@app.get("/health")
@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "aegis",
        "fortyguard_mode": "live" if settings.fortyguard_live else "cached",
        "llm_model": settings.primary_model_label(),
    }


# 2. Mount Static Frontend if exported (Docker & Hugging Face Spaces unified container)
for out_dir in [
    Path("/app/frontend/out"),
    Path(__file__).resolve().parents[2] / "frontend" / "out",
]:
    if out_dir.exists():
        app.mount("/", StaticFiles(directory=str(out_dir), html=True), name="frontend")
        break
