"""Back-office: the unclosed-leads queue, hand-off to a human, audit log, retention and erasure (admin)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..advisor import sessions
from ..backoffice import leads
from ..privacy import audit, retention
from .staff import require_staff

router = APIRouter(tags=["backoffice"])
STAFF = [Depends(require_staff)]


class HandoffIn(BaseModel):
    session_id: str
    reason: str = Field("Owner asked to talk to a human", max_length=200)


class RetentionIn(BaseModel):
    rejected_days: int | None = Field(None, ge=0)
    verified_days: int | None = Field(None, ge=0)


@router.get("/backoffice/leads", dependencies=STAFF)
def list_leads(status: str = Query("unclosed"), limit: int = Query(200, ge=1, le=1000), include_sample: bool = True) -> list[dict]:
    if status != "unclosed":
        raise HTTPException(400, "only status=unclosed is supported")
    audit.log("staff", "backoffice.leads", f"limit={limit}")
    return leads.queue(limit, include_sample)


@router.get("/backoffice/leads/{lead_id}/score", dependencies=STAFF)
def lead_score(lead_id: str) -> dict:
    d = leads.detail(lead_id)
    if not d:
        raise HTTPException(404, "unknown lead or session")
    audit.log("staff", "backoffice.score", lead_id)
    return d


@router.post("/backoffice/handoff", status_code=201)
def handoff(body: HandoffIn) -> dict:
    """'Talk to a human': the session goes to the field team's queue with the full profile."""
    s = sessions.get(body.session_id)
    if not s:
        raise HTTPException(404, "unknown session")
    if s["status"] == "erased":
        raise HTTPException(410, "this session's data was erased at the owner's request")
    sessions.set_status(body.session_id, "handoff", body.reason)
    audit.log("owner", "handoff.requested", body.session_id)
    return {"session_id": body.session_id, "status": "handoff", "reason": body.reason}


@router.get("/backoffice/audit", dependencies=STAFF)
def audit_log(limit: int = Query(50, ge=1, le=500)) -> list[dict]:
    return audit.recent(limit)


@router.post("/admin/retention/run", dependencies=STAFF)
def run_retention(body: RetentionIn | None = None) -> dict:
    body = body or RetentionIn()
    result = retention.purge(rejected_days=body.rejected_days, verified_days=body.verified_days)
    audit.log("admin", "retention.run", f"removed={len(result['removed'])} kept={result['kept']}")
    return result


@router.post("/admin/erase/{session_id}", dependencies=STAFF)
def erase(session_id: str) -> dict:
    """Data-principal erasure request (DPDP): delete images and transcript now; keep only the regulatory KYC record."""
    if not sessions.exists(session_id):
        raise HTTPException(404, "unknown session")
    result = retention.erase_session(session_id)
    audit.log("owner", "erasure.requested", session_id)
    return result
