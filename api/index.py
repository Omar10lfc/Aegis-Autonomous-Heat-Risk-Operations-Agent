import os
import sys
from pathlib import Path

# Add backend directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

os.environ.setdefault("FORTYGUARD_LIVE", "true")

from app.main import app
