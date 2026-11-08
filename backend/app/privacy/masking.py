"""Identifier masking for UI, API responses and logs. One implementation, reused by the KYC report."""
import hashlib
import re

from ..kyc.report import mask_gstin, mask_name, mask_udyam  # noqa: F401  (re-exported: single source of truth)

GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
UDYAM_RE = re.compile(r"\bUDYAM-[A-Z]{2}-\d{2}-\d{7}\b", re.I)
PHONE_RE = re.compile(r"(?<!\d)(\+91[\s-]?)?[6-9]\d{9}(?!\d)")


def mask_phone(p: str) -> str:
    digits = re.sub(r"\D", "", p or "")
    return f"XXXXXX{digits[-4:]}" if len(digits) >= 10 else "XXXXXXXXXX"


def hash_for_log(value: str, salt: str = "udyam-digital") -> str:
    """Stable, non-reversible token for names and free text in logs (first 12 hex chars of a salted SHA-256)."""
    return hashlib.sha256(f"{salt}:{(value or '').strip().lower()}".encode()).hexdigest()[:12]


def mask_text(text: str) -> str:
    """Mask every GSTIN, Udyam number and phone number inside free text."""
    text = GSTIN_RE.sub(lambda m: mask_gstin(m.group()), text or "")
    text = UDYAM_RE.sub(lambda m: mask_udyam(m.group().upper()), text)
    return PHONE_RE.sub(lambda m: mask_phone(m.group()), text)


def mask_session(session_id: str) -> str:
    return (session_id or "")[:6] + "…" if session_id else ""
