"""Sessions and the advisor chat."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..advisor import sessions
from ..advisor.chat import step
from ..advisor.explain import explain
from ..advisor.tools import missing_fields, rec_payload

router = APIRouter(tags=["advisor"])


class NewSession(BaseModel):
    language: str = Field("en", description="en | hi | hinglish (the advisor also auto-detects from what the owner types)")
    partner_code: str | None = None
    referrer: str | None = Field(None, description="session id of the customer who referred this one")


class ChatIn(BaseModel):
    session_id: str
    text: str = Field(..., min_length=1, max_length=2000)


def session_view(sid: str) -> dict:
    s = sessions.get(sid)
    if not s:
        raise HTTPException(404, "unknown session")
    return s


@router.post("/sessions", status_code=201)
def create_session(body: NewSession) -> dict:
    sid = sessions.create(body.language, body.partner_code, body.referrer)
    return {"session_id": sid, "language": body.language, "partner_code": body.partner_code}


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    return session_view(session_id)


@router.post("/advisor/chat")
def chat(body: ChatIn) -> dict:
    """One owner message in, one advisor reply out. The recommendation (when present) is the rules-engine result;
    the UI renders its card from `recommendation`, never from the prose."""
    try:
        st = sessions.state(body.session_id)
    except KeyError:
        raise HTTPException(404, "unknown session") from None
    s = sessions.get(body.session_id)
    if s and s["status"] == "erased":
        raise HTTPException(410, "this session's data was erased at the owner's request")
    reply = step(st, body.text)
    sessions.save(body.session_id, st)
    rec = st.recommendation
    return {
        "session_id": body.session_id,
        "text": reply,
        "language": st.language,
        "provider": st.provider,
        "profile": st.profile.model_dump(mode="json"),
        "missing": missing_fields(st.profile, st),
        "recommendation": rec_payload(rec, st.quantities) if rec else None,
        "explanation": {"en": explain(rec, "en"), "hi": explain(rec, "hi")} if rec else None,
        "usage": st.usage,
    }
