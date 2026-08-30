import os
import sys
from pathlib import Path

# Add backend directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

# Enforce FORTYGUARD_LIVE = false by default on Vercel unless explicitly overridden
os.environ.setdefault("FORTYGUARD_LIVE", "false")

from app.main import app
