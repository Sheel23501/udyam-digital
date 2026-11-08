"""Document field extraction with Gemini vision + a Pydantic response schema. Results are cached on disk by image
hash, so a known image never hits the network twice (and the demo works offline for the 47 sample documents)."""
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path

from google import genai
from google.genai import types

from ..config import CACHE_DIR, GEMINI_API_KEY, GEMINI_VISION_MODEL
from .schemas import SCHEMAS

log = logging.getLogger(__name__)
CACHE = Path(CACHE_DIR) / "extractions"
CACHE.mkdir(parents=True, exist_ok=True)
_client: genai.Client | None = None

PROMPT = (
    "You are transcribing a scanned Indian business KYC document. Copy every requested field EXACTLY as printed: "
    "do not correct spelling, digits, dates or names, even if they look wrong. Dates must be YYYY-MM-DD. "
    "If a value wraps onto a second line, join the lines into one value (e.g. 'Maharashtr' + 'a - 411231' is 'Maharashtra - 411231'). "
    "If a field is blank, absent or cannot be read, write UNREADABLE. For gstin_confidence give a number from 0 to 1 "
    "for how sure you are that every character of the GSTIN was read correctly (use below 0.9 if any character is doubtful)."
)
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

# Free tier allows 5 requests/minute per model. Space calls out and back off on 429 so a batch run never dies.
MIN_INTERVAL_S = float(os.getenv("GEMINI_MIN_INTERVAL_S", "13"))
MAX_ATTEMPTS = int(os.getenv("GEMINI_MAX_ATTEMPTS", "6"))
_last_call = 0.0


def _throttle() -> None:
    global _last_call
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _retry_delay(err: Exception, attempt: int) -> float:
    m = re.search(r"retry in ([0-9.]+)s", str(err), re.IGNORECASE)
    return (float(m.group(1)) + 1.0) if m else min(60.0, 10.0 * (attempt + 1))


def _client_() -> genai.Client:
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set")
        # v1beta is required for JSON mode / response_schema on the Gemini Developer API
        _client = genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(api_version="v1beta"))
    return _client


def image_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cached(doc_type: str, key: str):
    p = CACHE / f"{key}.json"
    if p.exists():
        return SCHEMAS[doc_type](**json.loads(p.read_text(encoding="utf-8")))
    return None


def extract(path: str, doc_type: str, use_cache: bool = True):
    """Return an instance of the schema for `doc_type` (GstCertificate, UdyamCertificate, SignatoryId, ElectricityBill)."""
    schema = SCHEMAS[doc_type]
    data = Path(path).read_bytes()
    key = image_hash(data)
    if use_cache:
        hit = cached(doc_type, key)
        if hit is not None:
            return hit
    mime = MIME.get(Path(path).suffix.lower(), "image/png")
    last_err: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            _throttle()
            resp = _client_().models.generate_content(
                model=GEMINI_VISION_MODEL,
                contents=[types.Part.from_bytes(data=data, mime_type=mime), PROMPT],
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0),
            )
            doc = resp.parsed if isinstance(resp.parsed, schema) else schema.model_validate_json(resp.text or "{}")
            (CACHE / f"{key}.json").write_text(json.dumps(doc.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
            return doc
        except Exception as e:                      # noqa: BLE001 — back off (rate limits) and retry, then surface
            last_err = e
            msg = str(e)
            transient = "429" in msg or "RESOURCE_EXHAUSTED" in msg or "503" in msg or "UNAVAILABLE" in msg
            log.warning("extraction attempt %d failed for %s: %s", attempt + 1, Path(path).name, msg[:160])
            if not transient:
                break
            time.sleep(_retry_delay(e, attempt))
    raise RuntimeError(f"extraction failed for {path}: {last_err}")
