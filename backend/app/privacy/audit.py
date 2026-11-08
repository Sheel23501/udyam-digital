"""Audit log: who did what to which subject. Subjects are masked before they are written; raw identifiers,
names and document bytes never reach this table."""
from datetime import datetime, timezone

from ..data.loader import connect
from .masking import mask_text


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(actor: str, action: str, subject: str = "") -> int:
    con = connect()
    cur = con.execute("INSERT INTO audit_log(ts, actor, action, subject_masked) VALUES (?,?,?,?)",
                      (now_iso(), actor[:40], action[:60], mask_text(str(subject))[:200]))
    con.commit()
    return int(cur.lastrowid)


def recent(limit: int = 50) -> list[dict]:
    rows = connect().execute("SELECT id, ts, actor, action, subject_masked FROM audit_log ORDER BY id DESC LIMIT ?",
                             (max(1, min(limit, 500)),)).fetchall()
    return [dict(r) for r in rows]
