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

# Advisor LLM: OpenAI-compatible providers tried in order (see app/llm/providers.py). Keys are read at call time.
ADVISOR_PROVIDER_CHAIN = os.getenv("ADVISOR_PROVIDER_CHAIN", "groq,cerebras,mistral,openrouter,gemini")
ADVISOR_MODEL_GROQ = os.getenv("ADVISOR_MODEL_GROQ", "openai/gpt-oss-120b")
ADVISOR_MODEL_CEREBRAS = os.getenv("ADVISOR_MODEL_CEREBRAS", "gpt-oss-120b")
ADVISOR_REASONING_EFFORT = os.getenv("ADVISOR_REASONING_EFFORT", "medium")
ADVISOR_MAX_WAIT_S = float(os.getenv("ADVISOR_MAX_WAIT_S", "20"))

TODAY = date.fromisoformat(os.getenv("TODAY", "2026-07-15"))
ADDRESS_PROOF_MAX_AGE_DAYS = 90

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "udyam.db"
CACHE_DIR = DATA_DIR / "cache"
UPLOAD_DIR = DATA_DIR / "uploads"

# Image gates, calibrated in Phase 4 against the 47 sample images (K04's GST cert is the blurred outlier,
# K02's GST cert the rotated one). Override via .env if you photograph your own documents.
BLUR_THRESHOLD = float(os.getenv("BLUR_THRESHOLD", "100"))
SKEW_THRESHOLD_DEG = float(os.getenv("SKEW_THRESHOLD_DEG", "2.0"))
