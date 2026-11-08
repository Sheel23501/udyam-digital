"""Demo cache: transcript-so-far -> reply + state snapshot.

Key = sha256 of the user turns so far (plus language). When every LLM provider fails live, the advisor serves the
cached reply for that exact transcript, so the three scripted demo conversations never depend on the network.
Entries for the demo conversations are committed to git (data/cache/advisor/)."""
import hashlib
import json
from pathlib import Path

from ..config import CACHE_DIR

ADVISOR_CACHE = CACHE_DIR / "advisor"


def key(turns: list[str], language: str) -> str:
    norm = [" ".join(t.split()).strip().lower() for t in turns]
    return hashlib.sha256(json.dumps({"lang": language, "turns": norm}, ensure_ascii=False).encode()).hexdigest()


def path(turns: list[str], language: str) -> Path:
    return ADVISOR_CACHE / f"{key(turns, language)}.json"


def get(turns: list[str], language: str) -> dict | None:
    p = path(turns, language)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def put(turns: list[str], language: str, entry: dict) -> Path:
    ADVISOR_CACHE.mkdir(parents=True, exist_ok=True)
    p = path(turns, language)
    p.write_text(json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8")
    return p
