"""Back-office queue: leads the digital journey could not close, scored for the field team.

Two sources: (a) live sessions that stopped before an order, (b) a reproducible sample of dropped leads from the
historical file, so the screen looks real on day one. The score is a transparent heuristic with its top reasons
(Phase 9 may swap in the trained propensity model behind the same `score()` signature). It only prioritises
outreach; it never denies anyone service."""
import random
from functools import lru_cache

from ..advisor import sessions
from ..data.loader import connect
from ..engine.bundles import infer_segment, recommend
from ..engine.models import Need, Profile

# How recoverable each historical drop reason is, with the action that addresses it.
DROP_REASONS: dict[str, tuple[float, str]] = {
    "Quote took too long to arrive": (0.85, "Send the instant one-number quote on WhatsApp"),
    "Quote too complex to understand": (0.80, "Send the one-number quote in their language"),
    "Visit not scheduled by sales": (0.80, "No visit needed: send the self-serve link"),
    "Owner had no time for a visit": (0.75, "Send the self-serve link; 5-minute journey on phone"),
    "Only wanted a mobile plan": (0.70, "Offer SIM-only plan; cross-sell later"),
    "Found paperwork too long": (0.70, "Send the 4-photo Smart KYC link"),
    "Missing GST or Udyam document": (0.60, "Offer the Udyam-only / GST-free path"),
    "Authorised signatory not available": (0.60, "Let the signatory complete KYC from their own phone"),
    "Installation delayed beyond 21 days": (0.60, "Offer AirFiber as a 2-day interim line"),
    "Site not feasible for fibre": (0.55, "Offer 5G AirFiber"),
    "Unreachable after 3 attempts": (0.50, "WhatsApp message with the self-serve link instead of calls"),
    "Decided to wait": (0.50, "30-day check-in with a no-contract SIM offer"),
    "First payment failed": (0.50, "Resend the payment link; offer UPI"),
    "Price too high": (0.35, "Send a right-sized bundle (engine minimum) and the savings vs current spend"),
    "Customer cancelled before install": (0.35, "Call to understand; offer faster AirFiber install"),
    "Document details did not match": (0.30, "Guide a re-upload with the correct legal name"),
    "Competitor offered cheaper plan": (0.30, "Match on bundle value, not price; show total cost"),
    "Locked in with current provider": (0.20, "Diary a call for the contract end date"),
    "Not interested on first call": (0.15, "Low priority: nurture by WhatsApp only"),
    "Wrong or invalid number": (0.05, "Verify number via the website form; do not call"),
}
STAGE_WEIGHT = {"Lead": 0.10, "Contacted": 0.25, "Needs assessed": 0.45, "Quote accepted": 0.70, "KYC complete": 0.85}
SESSION_STATUS_WEIGHT = {"open": 0.20, "quoted": 0.55, "consented": 0.70, "kyc_review": 0.75, "kyc_fail": 0.45, "handoff": 0.90, "kyc_pass": 0.95}
SESSION_ACTION = {
    "open": "Owner left during the chat: WhatsApp the link to resume",
    "quoted": "Quote shown but not accepted: call with the one-number price",
    "consented": "Consent given, KYC not started: send the 4-photo KYC link",
    "kyc_review": "KYC needs a re-upload: guide the owner on which photo",
    "kyc_fail": "KYC failed: a human must check the documents",
    "handoff": "Owner asked for a human: call back today",
    "kyc_pass": "Verified, order not placed: call to close",
}


def _int(v, default=0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def lead_profile(row: dict) -> Profile:
    products = [p for p in (row.get("products_of_interest") or "").split(";") if p]
    needs = [Need.SIM_ONLY] if row.get("drop_reason") == "Only wanted a mobile plan" else []
    return Profile(business_type=row.get("business_type"), employee_count=_int(row.get("employee_count"), 1),
                   num_sites=_int(row.get("num_sites"), 1), city=row.get("city"),
                   has_gstin=(row.get("has_gstin") == "Y"), requested_products=products, needs=needs)


@lru_cache(maxsize=4096)
def _value_for(lead_id: str) -> int:
    row = connect().execute("SELECT * FROM smb_leads WHERE lead_id = ?", (lead_id,)).fetchone()
    return recommend(lead_profile(dict(row))).monthly_min if row else 0


def score_lead(row: dict) -> dict:
    recover, action = DROP_REASONS.get(row.get("drop_reason") or "", (0.40, "Call back with the self-serve link"))
    stage = STAGE_WEIGHT.get(row.get("stage_reached") or "", 0.1)
    gst = 1.0 if row.get("has_gstin") == "Y" else 0.3
    spend = _int(row.get("monthly_telecom_spend_inr"))
    value = min(1.0, spend / 5000) if spend else 0.3
    score = round(0.45 * recover + 0.30 * stage + 0.10 * gst + 0.15 * value, 2)
    reasons = sorted([
        (0.45 * recover, f"drop reason is {'recoverable' if recover >= 0.5 else 'hard to recover'}: {row.get('drop_reason') or 'unknown'}"),
        (0.30 * stage, f"reached stage '{row.get('stage_reached') or 'Lead'}'"),
        (0.10 * gst, "GST registered: full catalogue eligible" if gst == 1.0 else "no GST: GST-free bundle only"),
        (0.15 * value, f"pays ₹{spend:,}/month today" if spend else "current spend unknown"),
    ], key=lambda x: -x[0])
    return {"score": score, "reasons": [r for _, r in reasons[:3]], "suggested_action": action}


def score_session(s: dict) -> dict:
    status = s.get("status") or "open"
    base = SESSION_STATUS_WEIGHT.get(status, 0.3)
    prof = s.get("profile") or {}
    gst = 1.0 if prof.get("has_gstin") else 0.3
    rec = s.get("recommendation") or {}
    value = min(1.0, (rec.get("monthly_min") or 0) / 5000) if rec else 0.3
    score = round(0.6 * base + 0.15 * gst + 0.25 * value, 2)
    reasons = [f"journey stopped at '{status}'" + (f": {s['handoff_reason']}" if s.get("handoff_reason") else ""),
               "GST registered" if gst == 1.0 else "no GST / unknown",
               f"quoted ₹{rec.get('monthly_min', 0):,}/month" if rec else "no quote yet"]
    return {"score": score, "reasons": reasons, "suggested_action": SESSION_ACTION.get(status, "Call back")}


def sample_dropped(n: int = 200, seed: int = 42) -> list[dict]:
    rows = [dict(r) for r in connect().execute(
        "SELECT lead_id, business_name, business_type, segment, city, city_tier, preferred_language, employee_count, num_sites, has_gstin, "
        "products_of_interest, stage_reached, drop_reason, monthly_telecom_spend_inr, lead_source, created_date "
        "FROM smb_leads WHERE outcome = 'Dropped' AND stage_reached != 'Lead' ORDER BY lead_id").fetchall()]
    random.Random(seed).shuffle(rows)
    out = []
    for r in rows[:n]:
        sc = score_lead(r)
        out.append({
            "id": r["lead_id"], "source": "lead", "business": r["business_name"], "business_type": r["business_type"],
            "segment": r["segment"], "city": r["city"], "language": r["preferred_language"],
            "est_monthly_value": _value_for(r["lead_id"]), "last_step": r["stage_reached"], "reason": r["drop_reason"],
            "lead_source": r["lead_source"], "partner": r["lead_source"] if r["lead_source"] == "Channel partner" else None,
            "score": sc["score"], "suggested_action": sc["suggested_action"], "date": r["created_date"],
        })
    return out


SEGMENT_LABEL = {"micro": "Micro retail & services", "prof": "Professional offices", "multi": "Small multi-site businesses", "mfg": "Small manufacturers"}


def live_sessions(limit: int = 200) -> list[dict]:
    out = []
    for s in sessions.unclosed(limit):
        prof = s.get("profile") or {}
        rec = s.get("recommendation") or {}
        sc = score_session(s)
        try:
            seg = SEGMENT_LABEL.get(infer_segment(Profile(**prof)), "")
        except Exception:  # noqa: BLE001 — a malformed stored profile must not break the queue
            seg = ""
        out.append({
            "id": s["session_id"], "source": "session", "business": prof.get("business_type") or "(not yet known)",
            "business_type": prof.get("business_type"), "segment": seg, "city": prof.get("city"), "language": s.get("language"),
            "est_monthly_value": rec.get("monthly_min") or 0, "last_step": s["status"],
            "reason": s.get("handoff_reason") or SESSION_ACTION.get(s["status"], ""), "lead_source": "Digital journey",
            "partner": s.get("partner_code"), "score": sc["score"], "suggested_action": sc["suggested_action"], "date": s["created"][:10],
        })
    return out


def queue(limit: int = 200, include_sample: bool = True) -> list[dict]:
    rows = live_sessions(limit) + (sample_dropped(limit) if include_sample else [])
    rows.sort(key=lambda r: (-r["score"], -r["est_monthly_value"]))
    return rows[:limit]


def detail(lead_id: str) -> dict | None:
    if lead_id.startswith("L"):
        row = connect().execute("SELECT * FROM smb_leads WHERE lead_id = ?", (lead_id,)).fetchone()
        if not row:
            return None
        r = dict(row)
        sc = score_lead(r)
        return {"id": lead_id, "source": "lead", "business": r["business_name"], "segment": r["segment"], "city": r["city"],
                "est_monthly_value": _value_for(lead_id), "last_step": r["stage_reached"], "reason": r["drop_reason"], **sc}
    s = sessions.get(lead_id)
    if not s:
        return None
    sc = score_session(s)
    return {"id": lead_id, "source": "session", "business": (s.get("profile") or {}).get("business_type"),
            "city": (s.get("profile") or {}).get("city"), "est_monthly_value": (s.get("recommendation") or {}).get("monthly_min") or 0,
            "last_step": s["status"], "reason": s.get("handoff_reason"), **sc}
