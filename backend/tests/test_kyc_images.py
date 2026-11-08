"""Image-level KYC tests. Gate tests need no network. The end-to-end test runs only when extraction results are cached
(scripts/kyc_report.py populates the cache) or a GEMINI_API_KEY is available."""
import glob
import json
import os
from pathlib import Path

import pytest

from app.config import CACHE_DIR, DATA_DIR, GEMINI_API_KEY
from app.kyc.extract import image_hash
from app.kyc.gates import gate, stats

DOCS = Path(DATA_DIR) / "kyc_documents"
KEY = json.loads((Path(__file__).parent / "kyc_answer_key_images.json").read_text(encoding="utf-8"))


def test_blur_gate_catches_only_k04():
    flagged = {Path(p).name for p in glob.glob(str(DOCS / "K*.png")) if (gate(p, "gst_certificate")[0] or object()).__class__.__name__ == "CheckResult" and gate(p, "gst_certificate")[0].code == "IMAGE_BLURRED"}
    assert flagged == {"K04_gst_certificate.png"}


def test_skew_gate_catches_only_k02():
    flagged = {Path(p).name for p in glob.glob(str(DOCS / "K*.png")) if (f := gate(p, "gst_certificate")[0]) and f.code == "IMAGE_SKEWED"}
    assert flagged == {"K02_gst_certificate.png"}


def test_clean_images_pass_gates():
    s = stats(str(DOCS / "K03_gst_certificate.png"))
    assert s.blur > 500 and abs(s.skew_deg) < 1


GATED = {"K02_gst_certificate.png", "K04_gst_certificate.png"}       # fail the image gates, never extracted


def _applicant_cached(app: str) -> bool:
    """True when every non-gated image of this applicant already has a cached extraction (tests never spend API quota)."""
    cache = Path(CACHE_DIR) / "extractions"
    paths = glob.glob(str(DOCS / f"{app}_*.png"))
    return bool(paths) and all(
        Path(p).name in GATED or (cache / f"{image_hash(Path(p).read_bytes())}.json").exists() for p in paths)


@pytest.mark.parametrize("app", [k for k in KEY if k.startswith("K")])
def test_image_pipeline_matches_answer_key(app):
    if not _applicant_cached(app):
        pytest.skip(f"{app}: extractions not cached yet (run scripts/kyc_report.py)")
    from app.kyc.images import run_images
    files = {Path(p).stem.split("_", 1)[1]: p for p in glob.glob(str(DOCS / f"{app}_*.png"))}
    r = run_images(app, files)
    flags = {c.code for c in r.checks if c.status in ("FAIL", "REVIEW")}
    assert r.verdict == KEY[app]["verdict"], f"{app}: {r.verdict}, flags={flags}"
    assert set(KEY[app]["codes"]) <= flags
