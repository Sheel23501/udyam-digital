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
    """Angle of the dominant text direction: length-weighted median of near-horizontal Hough segments.
    0 = upright. Returns 0 when there is too little horizontal structure to judge (never flag on thin evidence)."""
    h, w = grey.shape[:2]
    if w and abs(w - TEMPLATE_WH[0]) > TEMPLATE_WH[0] * 0.15:        # phone photos come in every size: normalise width first
        f = TEMPLATE_WH[0] / w
        grey = cv2.resize(grey, (TEMPLATE_WH[0], max(1, int(round(h * f)))), interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)
        h, w = grey.shape[:2]
    edges = cv2.Canny(grey, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 720, threshold=80, minLineLength=max(40, w // 10), maxLineGap=12)
    if lines is None:
        return 0.0
    segs: list[tuple[float, float]] = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):   # OpenCV 4 gives (N,1,4), OpenCV 5 gives (N,4)
        a = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if -45 < a < 45:                                      # near-horizontal: text baselines, table rules
            segs.append((a, float(np.hypot(x2 - x1, y2 - y1))))
    if not segs or sum(length for _, length in segs) < 1.5 * w:
        return 0.0
    segs.sort()
    total = sum(length for _, length in segs)
    acc = 0.0
    for a, length in segs:                                    # length-weighted median
        acc += length
        if acc >= total / 2:
            return a
    return segs[-1][0]


def normalise(grey: np.ndarray) -> np.ndarray:
    """Bring any photo to the specimen width so blur and skew thresholds mean the same thing for a 700 px screenshot
    and a 4000 px camera photo."""
    h, w = grey.shape[:2]
    if not w or abs(w - TEMPLATE_WH[0]) <= TEMPLATE_WH[0] * 0.15:
        return grey
    f = TEMPLATE_WH[0] / w
    return cv2.resize(grey, (TEMPLATE_WH[0], max(1, int(round(h * f)))), interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)


def stats(path: str) -> ImageStats:
    g = _grey(path)
    h, w = g.shape[:2]
    n = normalise(g)
    return ImageStats(width=w, height=h, blur=blur_score(n), skew_deg=skew_angle(n))


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
