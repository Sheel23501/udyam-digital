"""Mock GSTIN and Udyam lookup APIs, backed by the provided registry CSVs.

In production these functions would call GSTN (via a GSP), the Udyam verification API and DigiLocker;
the interface is deliberately the same so the adapters can be swapped without touching KYC logic.
"""
from ..data.loader import connect


def gstin_lookup(gstin: str) -> dict | None:
    """Return the registry record for a GSTIN or None. Keys: gstin, legal_name, trade_name, constitution,
    principal_place_of_business, state, registration_date, status (Active | Cancelled | Suspended)."""
    if not gstin:
        return None
    row = connect().execute("SELECT * FROM mock_gstin_registry WHERE gstin = ?", (gstin.strip().upper(),)).fetchone()
    return dict(row) if row else None


def gstin_by_name(name: str) -> list[dict]:
    """Case-insensitive search on trade or legal name (used to surface tampering evidence, never to auto-correct)."""
    if not name or not name.strip():
        return []
    q = f"%{name.strip()}%"
    rows = connect().execute(
        "SELECT * FROM mock_gstin_registry WHERE trade_name LIKE ? COLLATE NOCASE OR legal_name LIKE ? COLLATE NOCASE LIMIT 20",
        (q, q),
    ).fetchall()
    return [dict(r) for r in rows]


def udyam_lookup(number: str) -> dict | None:
    """Return the Udyam record or None. Keys: udyam_number, enterprise_name, enterprise_type, major_activity,
    nic_description, state, city, date_of_registration."""
    if not number:
        return None
    row = connect().execute("SELECT * FROM mock_udyam_registry WHERE udyam_number = ?", (number.strip().upper(),)).fetchone()
    return dict(row) if row else None


def lead_contact_for(gstin: str | None = None, udyam: str | None = None) -> dict | None:
    """The CRM's person of record for a business (from smb_leads). Used for LLP / Pvt Ltd signatory checks."""
    con = connect()
    row = None
    if gstin:
        row = con.execute(
            "SELECT lead_id, business_name, contact_name, contact_role, city, state FROM smb_leads WHERE gstin = ? LIMIT 1",
            (gstin.strip().upper(),),
        ).fetchone()
    if row is None and udyam:
        row = con.execute(
            "SELECT lead_id, business_name, contact_name, contact_role, city, state FROM smb_leads WHERE udyam_number = ? LIMIT 1",
            (udyam.strip().upper(),),
        ).fetchone()
    return dict(row) if row else None


def registry_status_counts() -> dict[str, int]:
    rows = connect().execute("SELECT status, COUNT(*) AS n FROM mock_gstin_registry GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rows}
