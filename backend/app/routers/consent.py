"""DPDP consent endpoints. KYC upload and run refuse (403) without an active consent for the session."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..advisor import sessions
from ..privacy import audit, consent

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
    if not sessions.exists(body.session_id):
        raise HTTPException(404, "unknown session")
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


@router.delete("/consent/{consent_id}")
def withdraw(consent_id: int) -> dict:
    rec = consent.withdraw(consent_id)
    if not rec:
        raise HTTPException(404, "unknown consent")
    audit.log("owner", "consent.withdrawn", rec["session_id"])
    return rec


def require_consent(session_id: str) -> dict:
    """Shared gate for the KYC endpoints."""
    if not sessions.exists(session_id):
        raise HTTPException(404, "unknown session")
    active = consent.active_for(session_id)
    if not active:
        raise HTTPException(403, {"message": "consent required before any document is processed",
                                  "how": "POST /consent with this session_id and all required purposes (see GET /consent/notice)"})
    return active
