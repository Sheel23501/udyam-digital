"""Verdict aggregation and identifier masking for the KYC report."""
from .schemas import CheckResult

ORDER = {"FAIL": 3, "REVIEW": 2, "WARN": 1, "PASS": 0}


def verdict(checks: list[CheckResult]) -> str:
    statuses = {c.status for c in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if "REVIEW" in statuses:
        return "REVIEW"
    return "PASS"


def mask_gstin(g: str) -> str:
    g = (g or "").upper()
    return f"{g[:2]}{'X' * 10}{g[-3:]}" if len(g) == 15 else "XXXXXXXXXXXXXXX"


def mask_udyam(u: str) -> str:
    u = (u or "").upper()
    return f"{u[:12]}XXXX{u[-3:]}" if len(u) >= 19 else "UDYAM-XX-XX-XXXXXXX"


def mask_name(n: str) -> str:
    parts = (n or "").split()
    return (parts[0] + (" " + parts[-1][0] + "." if len(parts) > 1 else "")) if parts else ""


def next_step(v: str, checks: list[CheckResult]) -> tuple[str, str]:
    if v == "PASS":
        return "Your business is verified. Continue to e-sign and place the order.", "आपका व्यवसाय सत्यापित हो गया। ई-साइन करके ऑर्डर पूरा करें।"
    worst = sorted((c for c in checks if c.status in ("FAIL", "REVIEW")), key=lambda c: -ORDER[c.status])
    if v == "REVIEW":
        return "Please re-upload the documents flagged above; nothing else is needed.", "ऊपर बताए दस्तावेज़ दोबारा अपलोड करें; और कुछ नहीं चाहिए।"
    return (f"Fix the {len(worst)} issue{'s' if len(worst) != 1 else ''} above and upload again, or tap 'Talk to a human' and we will call you.",
            f"ऊपर बताई {len(worst)} समस्या ठीक करके दोबारा अपलोड करें, या 'किसी व्यक्ति से बात करें' दबाएँ।")
