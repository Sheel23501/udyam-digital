"""Mock registry lookups (GSTN / Udyam). Rate-limited, audited, and always masked in the response."""
import re
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request

from ..kyc.checksum import checksum_ok, format_ok
from ..lookup.registry import gstin_lookup, udyam_lookup
from ..privacy import audit
from ..privacy.masking import mask_gstin, mask_name, mask_udyam

router = APIRouter(tags=["lookup"])

RATE_LIMIT = 30            # requests
RATE_WINDOW_S = 60.0
_hits: dict[str, deque] = defaultdict(deque)
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")


def _rate_limit(request: Request) -> None:
    key = request.client.host if request.client else "anon"
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > RATE_WINDOW_S:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, f"too many lookups: max {RATE_LIMIT} per minute")
    q.append(now)


@router.get("/lookup/gstin/{gstin}")
def lookup_gstin(gstin: str, request: Request) -> dict:
    _rate_limit(request)
    g = re.sub(r"\s", "", gstin).upper()
    if not format_ok(g):
        raise HTTPException(400, "not a valid GSTIN format (15 characters: 2 digits, 5 letters, 4 digits, letter, entity code, Z, check char)")
    if not checksum_ok(g):
        audit.log("api", "lookup.gstin", f"{g} checksum-fail")
        return {"found": False, "gstin_masked": mask_gstin(g), "checksum_ok": False, "status": None}
    row = gstin_lookup(g)
    audit.log("api", "lookup.gstin", f"{g} {'found' if row else 'not-found'}")
    if not row:
        return {"found": False, "gstin_masked": mask_gstin(g), "checksum_ok": True, "status": None}
    return {"found": True, "gstin_masked": mask_gstin(g), "checksum_ok": True, "status": row["status"],
            "trade_name": row["trade_name"], "legal_name_masked": mask_name(row["legal_name"]), "constitution": row["constitution"],
            "state": row["state"], "registration_date": row["registration_date"]}


@router.get("/lookup/udyam/{number}")
def lookup_udyam(number: str, request: Request) -> dict:
    _rate_limit(request)
    u = re.sub(r"\s", "", number).upper()
    if not UDYAM_RE.match(u):
        raise HTTPException(400, "not a valid Udyam number (UDYAM-XX-00-0000000)")
    row = udyam_lookup(u)
    audit.log("api", "lookup.udyam", f"{u} {'found' if row else 'not-found'}")
    if not row:
        return {"found": False, "udyam_masked": mask_udyam(u)}
    out = {"found": True, "udyam_masked": mask_udyam(u)}
    for k in ("enterprise_name", "enterprise_type", "major_activity", "state", "city", "date_of_registration", "status"):
        if k in row.keys():
            out[k] = row[k]
    return out
