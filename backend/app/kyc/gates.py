"""Image-quality gates run before any extraction. A document that fails a gate gets REVIEW ("please re-take the photo")
rather than a FAIL, because the problem is the photo, not the business."""
from dataclasses import dataclass

import cv2
import numpy as np

from ..config import BLUR_THRESHOLD, SKEW_THRESHOLD_DEG
from .schemas import CheckResult

TEMPLATE_WH = (1240, 1754)     # every clean specimen in the pack is A4 at this size
MAX_SIDE = 6000


@dataclass
class ImageStats:
    width: int
    height: int
    blur: float          # variance of Laplacian on the grey page; low = blurred
    skew_deg: float      # dominant text-line angle; |angle| > threshold = rotated scan


def _grey(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"cannot read image: {path}")
    return img


def blur_score(grey: np.ndarray) -> float:
    return float(cv2.Laplacian(grey, cv2.CV_64F).var())


def skew_angle(grey: np.ndarray) -> float:
    """Angle of the dominant text direction via Hough lines on edges. 0 = upright. Robust to margins and logos."""
    edges = cv2.Canny(grey, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=120, minLineLength=grey.shape[1] // 6, maxLineGap=20)
    if lines is None:
        return 0.0
    angles = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):   # OpenCV 4 gives (N,1,4), OpenCV 5 gives (N,4)
        a = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if -45 < a < 45:                      # near-horizontal lines only (text baselines, table rules)
            angles.append(a)
    return float(np.median(angles)) if angles else 0.0


def stats(path: str) -> ImageStats:
    g = _grey(path)
    h, w = g.shape[:2]
    return ImageStats(width=w, height=h, blur=blur_score(g), skew_deg=skew_angle(g))


def gate(path: str, doc_type: str) -> tuple[CheckResult | None, ImageStats]:
    s = stats(path)
    pretty = doc_type.replace("_", " ")
    hi = {"gst_certificate": "GST प्रमाणपत्र", "udyam_certificate": "उद्यम प्रमाणपत्र", "signatory_id": "आईडी", "address_proof": "पते का प्रमाण"}.get(doc_type, "दस्तावेज़")
    if max(s.width, s.height) > MAX_SIDE:
        return CheckResult(code="IMAGE_TOO_LARGE", status="REVIEW", evidence=f"{s.width}x{s.height}",
                           message_en=f"Your {pretty} image is too large to process. Please upload a smaller photo.",
                           message_hi=f"{hi} की फ़ोटो बहुत बड़ी है। कृपया छोटी फ़ोटो दें।"), s
    if s.blur < BLUR_THRESHOLD:
        return CheckResult(code="IMAGE_BLURRED", status="REVIEW", evidence=f"blur={s.blur:.0f} < {BLUR_THRESHOLD:.0f}",
                           message_en=f"Your {pretty} is blurred, so we cannot read it reliably. Please re-take the photo holding the phone still, in good light.",
                           message_hi=f"{hi} की फ़ोटो धुंधली है। कृपया फ़ोन स्थिर रखकर, अच्छी रोशनी में दोबारा फ़ोटो लें।"), s
    if abs(s.skew_deg) > SKEW_THRESHOLD_DEG:
        return CheckResult(code="IMAGE_SKEWED", status="REVIEW", evidence=f"skew={s.skew_deg:.1f}° ({s.width}x{s.height})",
                           message_en=f"Your {pretty} is rotated/tilted. Please place the document flat and photograph it straight on.",
                           message_hi=f"{hi} की फ़ोटो तिरछी है। कृपया दस्तावेज़ सीधा रखकर फ़ोटो लें।"), s
    return None, s
