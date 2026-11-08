"""Central configuration. Values come from the project-root .env (loaded here) or the environment."""
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]  # udyam-digital/
load_dotenv(_ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", GEMINI_MODEL)

TODAY = date.fromisoformat(os.getenv("TODAY", "2026-07-15"))
ADDRESS_PROOF_MAX_AGE_DAYS = 90

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "udyam.db"
CACHE_DIR = DATA_DIR / "cache"
UPLOAD_DIR = DATA_DIR / "uploads"

# Calibrated in Phase 4 against the 47 sample images (K04's GST cert is the blurred outlier).
BLUR_THRESHOLD = float(os.getenv("BLUR_THRESHOLD", "100"))
