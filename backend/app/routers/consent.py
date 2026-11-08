"""DPDP consent endpoints. KYC upload and run refuse (403) without an active consent for the session."""
from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ..advisor import sessions
from ..privacy import audit, consent, retention

router = APIRouter(tags=["consent"])


class ConsentIn(BaseModel):
    session_id: str
    purposes: list[str] = Field(..., description="ids from GET /consent/notice; all required ones must be present")
    language: str = "en"
    notice_version: str = consent.NOTICE_VERSION


@router.get("/consent/notice")
def notice(lang: str = Query("en", pattern="^(en|hi|hinglish)$")) -> dict:
    return consent.notice("hi" if lang == "hi" else "en")


@router.post("/consent", status_code=201)
def give_consent(body: ConsentIn) -> dict:
    s = sessions.get(body.session_id)
    if not s:
        raise HTTPException(404, "unknown session")
    if s["status"] == "erased":
        raise HTTPException(410, "this session's data was erased at the owner's request")
    missing = consent.missing_required(body.purposes)
    if missing:
        raise HTTPException(400, {"message": "required purposes missing", "missing": missing})
    unknown = sorted(set(body.purposes) - {p["id"] for p in consent.PURPOSES})
    if unknown:
        raise HTTPException(400, {"message": "unknown purposes", "unknown": unknown})
    rec = consent.record(body.session_id, body.purposes, body.language, body.notice_version)
    s = sessions.get(body.session_id)
    if s and s["status"] in ("open", "quoted"):
        sessions.set_status(body.session_id, "consented")
    audit.log("owner", "consent.given", body.session_id)
    return rec


@router.get("/consent/{session_id}")
def consent_status(session_id: str) -> dict:
    if not sessions.exists(session_id):
        raise HTTPException(404, "unknown session")
    return {"session_id": session_id, "active": consent.active_for(session_id), "history": consent.history(session_id)}


@router.delete("/consent/{session_id}/{consent_id}")
def withdraw(session_id: str, consent_id: int = Path(..., ge=1, le=2**62)) -> dict:
    """Withdraw a consent. The session id proves ownership (consent ids alone are sequential). Withdrawal stops
    processing and deletes the uploaded images and the chat transcript; the regulatory KYC record stays."""
    rec = consent.withdraw(consent_id, session_id)
    if not rec:
        raise HTTPException(404, "unknown consent for this session")
    rec["cleanup"] = retention.after_withdrawal(session_id)
    audit.log("owner", "consent.withdrawn", session_id)
    return rec


def require_consent(session_id: str) -> dict:
    """Shared gate for the KYC endpoints."""
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(404, "unknown session")
    if s["status"] == "erased":
        raise HTTPException(410, "this session's data was erased at the owner's request")
    active = consent.active_for(session_id)
    if not active:
        raise HTTPException(403, {"message": "consent required before any document is processed",
                                  "how": "POST /consent with this session_id and all required purposes (see GET /consent/notice)"})
    return active
