"""Orders: created from a session's engine-validated bundle; tracked through fixed stages with expected dates."""
import json
import uuid
from datetime import datetime, timezone

from ..advisor import sessions
from ..data.loader import connect
from ..engine.bundles import price_summary, validate
from ..engine.catalogue import catalogue
from ..engine.models import Profile
from . import tracker


class OrderError(ValueError):
    def __init__(self, status_code: int, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create(session_id: str, items: dict[str, int] | None = None, require_kyc_pass: bool = True) -> dict:
    sess = sessions.get(session_id)
    if not sess:
        raise OrderError(404, "unknown session")
    if sess.get("order_id"):
        raise OrderError(409, {"message": "this session already has an order", "order_id": sess["order_id"]})
    if sess.get("status") == "erased":
        raise OrderError(410, "this session's data was erased at the owner's request")
    from ..privacy import consent                             # noqa: PLC0415
    if not consent.active_for(session_id):
        raise OrderError(403, {"message": "consent required: the owner has not consented or has withdrawn consent"})
    if require_kyc_pass and sess.get("kyc_verdict") != "PASS":
        raise OrderError(409, {"message": "KYC must be PASS before an order can be placed", "kyc_verdict": sess.get("kyc_verdict")})
    prof = Profile(**(sess.get("profile") or {}))
    if items is None:
        rec = sess.get("recommendation") or {}
        items = {i["product_id"]: i["qty"] for i in rec.get("items", [])}
    items = {k: int(v) for k, v in items.items() if int(v) > 0}
    if not items:
        raise OrderError(400, "nothing to order: no recommendation on this session and no items given")
    v = validate(items, prof)
    if v.violations:
        raise OrderError(400, {"message": "bundle breaks eligibility rules", "violations": [x.model_dump(mode="json") for x in v.violations]})
    cat = catalogue()
    price = price_summary(items)
    bundle = {"items": [{"product_id": p, "name": cat[p].name, "qty": q, "unit": cat[p].unit,
                         "price_min": cat[p].price_min, "price_max": cat[p].price_max} for p, q in items.items()], **price}
    created = _now()
    order_id = "ORD-" + uuid.uuid4().hex[:8].upper()
    con = connect()
    con.execute("INSERT INTO orders(id, session_id, bundle_json, status, created, eta_json) VALUES (?,?,?,?,?,?)",
                (order_id, session_id, json.dumps(bundle), "PLACED", created.isoformat(timespec="seconds"),
                 json.dumps(tracker.eta(created, price["install_days"]))))
    con.commit()
    sessions.set_status(session_id, "ordered")
    return get(order_id)


def get(order_id: str) -> dict | None:
    row = connect().execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        return None
    status = row["status"]
    return {
        "order_id": row["id"], "session_id": row["session_id"], "status": status, "created": row["created"],
        "stages": tracker.STAGES, "stage_index": tracker.STAGES.index(status) if status in tracker.STAGES else 0,
        "progress": tracker.progress(status), "labels": tracker.LABELS,
        "eta": json.loads(row["eta_json"] or "{}"), "bundle": json.loads(row["bundle_json"] or "{}"),
    }


def advance(order_id: str) -> dict | None:
    row = connect().execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        return None
    nxt = tracker.next_stage(row["status"])
    con = connect()
    con.execute("UPDATE orders SET status = ? WHERE id = ?", (nxt, order_id))
    con.commit()
    return get(order_id)


def for_session(session_id: str) -> dict | None:
    row = connect().execute("SELECT id FROM orders WHERE session_id = ? ORDER BY created DESC LIMIT 1", (session_id,)).fetchone()
    return get(row["id"]) if row else None
