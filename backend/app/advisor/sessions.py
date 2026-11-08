"""Session store: one row per owner journey, with the advisor State persisted as JSON so the API is stateless
across restarts. Hot States are kept in memory to avoid re-parsing on every turn."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from ..data.loader import connect
from .state import State

_STATES: dict[str, State] = {}
STATUSES = ("open", "quoted", "consented", "kyc_pass", "kyc_review", "kyc_fail", "ordered", "handoff", "erased")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_columns() -> None:
    con = connect()
    cols = {r[1] for r in con.execute("PRAGMA table_info(sessions)").fetchall()}
    for col, ddl in (("handoff_reason", "TEXT"), ("updated", "TEXT"), ("phone_hash", "TEXT"), ("phone_masked", "TEXT"),
                     ("phone_verified", "INTEGER DEFAULT 0")):
        if col not in cols:
            try:
                con.execute(f"ALTER TABLE sessions ADD COLUMN {col} {ddl}")
            except sqlite3.OperationalError:
                pass
    con.commit()


def create(language: str = "en", partner_code: str | None = None, referrer: str | None = None, phone: dict | None = None) -> str:
    """phone: the identity from a verified OTP ({phone_hash, phone_masked}); the raw number is never stored."""
    _ensure_columns()
    sid = uuid.uuid4().hex[:12]
    con = connect()
    con.execute("INSERT INTO sessions(id, created, updated, language, partner_code, referrer, status, phone_hash, phone_masked, phone_verified) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sid, now_iso(), now_iso(), language, partner_code, referrer, "open",
                 (phone or {}).get("phone_hash"), (phone or {}).get("phone_masked"), 1 if phone else 0))
    con.commit()
    _STATES[sid] = State(language=language if language in ("en", "hi", "hinglish") else "en")
    return sid


def exists(session_id: str) -> bool:
    return connect().execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone() is not None


def get(session_id: str) -> dict | None:
    _ensure_columns()
    row = connect().execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    out = {
        "session_id": d["id"], "created": d["created"], "updated": d.get("updated"), "language": d["language"],
        "partner_code": d["partner_code"], "referrer": d["referrer"], "status": d["status"], "handoff_reason": d.get("handoff_reason"),
        "phone_masked": d.get("phone_masked"), "phone_verified": bool(d.get("phone_verified")),
        "profile": json.loads(d["profile_json"]) if d["profile_json"] else None,
        "recommendation": json.loads(d["recommendation_json"]) if d["recommendation_json"] else None,
    }
    kyc = connect().execute("SELECT id, verdict, ts FROM kyc_applications WHERE session_id = ? ORDER BY ts DESC, rowid DESC LIMIT 1",
                            (session_id,)).fetchone()
    out["kyc_application_id"] = kyc["id"] if kyc else None
    out["kyc_verdict"] = kyc["verdict"] if kyc else None
    order = connect().execute("SELECT id, status FROM orders WHERE session_id = ? ORDER BY created DESC LIMIT 1", (session_id,)).fetchone()
    out["order_id"] = order["id"] if order else None
    out["order_status"] = order["status"] if order else None
    cons = connect().execute("SELECT id FROM consents WHERE session_id = ? AND withdrawn_ts IS NULL ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
    out["consent_id"] = cons["id"] if cons else None
    return out


def state(session_id: str) -> State:
    """The advisor State for a session: from memory, else rebuilt from the persisted JSON. KeyError if unknown."""
    if session_id in _STATES:
        return _STATES[session_id]
    row = connect().execute("SELECT language, history_json FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise KeyError(session_id)
    st = State.from_dict(json.loads(row["history_json"])) if row["history_json"] else State(language=row["language"] or "en")
    _STATES[session_id] = st
    return st


def save(session_id: str, st: State) -> None:
    con = connect()
    row = con.execute("SELECT status FROM sessions WHERE id = ?", (session_id,)).fetchone()
    status = row["status"] if row else "open"
    if status == "open" and st.recommendation is not None:
        status = "quoted"
    con.execute("UPDATE sessions SET profile_json = ?, recommendation_json = ?, history_json = ?, language = ?, status = ?, updated = ? WHERE id = ?",
                (st.profile.model_dump_json(), st.recommendation.model_dump_json() if st.recommendation else None,
                 json.dumps(st.to_dict(), ensure_ascii=False), st.language, status, now_iso(), session_id))
    con.commit()
    _STATES[session_id] = st


def set_status(session_id: str, status: str, handoff_reason: str | None = None) -> None:
    if status not in STATUSES:
        raise ValueError(status)
    _ensure_columns()
    con = connect()
    if handoff_reason is not None:
        con.execute("UPDATE sessions SET status = ?, handoff_reason = ?, updated = ? WHERE id = ?", (status, handoff_reason, now_iso(), session_id))
    else:
        con.execute("UPDATE sessions SET status = ?, updated = ? WHERE id = ?", (status, now_iso(), session_id))
    con.commit()


def unclosed(limit: int = 200) -> list[dict]:
    """Sessions that did not end in an order (for the back-office queue), newest first."""
    _ensure_columns()
    rows = connect().execute(
        "SELECT * FROM sessions WHERE status NOT IN ('ordered', 'erased') ORDER BY COALESCE(updated, created) DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        out.append({
            "session_id": d["id"], "created": d["created"], "updated": d.get("updated"), "language": d["language"],
            "partner_code": d["partner_code"], "status": d["status"], "handoff_reason": d.get("handoff_reason"),
            "profile": json.loads(d["profile_json"]) if d["profile_json"] else {},
            "recommendation": json.loads(d["recommendation_json"]) if d["recommendation_json"] else None,
        })
    return out
