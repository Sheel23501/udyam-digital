"""Load the four provided CSVs into SQLite once, and create the app's own tables.

The CSVs are the source of truth for catalogue, leads and both mock registries; the
app tables (sessions, consents, kyc_applications, orders, audit_log) are written at runtime.
"""
import sqlite3
from functools import lru_cache

import pandas as pd

from ..config import DATA_DIR, DB_PATH

SOURCE_TABLES = ["product_catalogue", "smb_leads", "mock_gstin_registry", "mock_udyam_registry"]

APP_SCHEMA = """
CREATE INDEX IF NOT EXISTS ix_gst   ON mock_gstin_registry(gstin);
CREATE INDEX IF NOT EXISTS ix_udy   ON mock_udyam_registry(udyam_number);
CREATE INDEX IF NOT EXISTS ix_lead  ON smb_leads(lead_id);
CREATE INDEX IF NOT EXISTS ix_lead_gst ON smb_leads(gstin);
CREATE INDEX IF NOT EXISTS ix_lead_udy ON smb_leads(udyam_number);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, created TEXT NOT NULL, language TEXT, partner_code TEXT, referrer TEXT,
  profile_json TEXT, recommendation_json TEXT, history_json TEXT, status TEXT DEFAULT 'open'
);
CREATE TABLE IF NOT EXISTS consents (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, purposes_json TEXT NOT NULL,
  language TEXT, notice_version TEXT, ts TEXT NOT NULL, withdrawn_ts TEXT
);
CREATE TABLE IF NOT EXISTS kyc_applications (
  id TEXT PRIMARY KEY, session_id TEXT, applicant TEXT, verdict TEXT, report_json TEXT, ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY, session_id TEXT, bundle_json TEXT, status TEXT, created TEXT NOT NULL, eta_json TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT, action TEXT, subject_masked TEXT
);
"""


def build_db(force: bool = False) -> None:
    """Create the SQLite file from the CSVs if it does not exist (or always, with force=True)."""
    if DB_PATH.exists() and not force:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        for name in SOURCE_TABLES:
            df = pd.read_csv(DATA_DIR / f"{name}.csv", dtype=str, keep_default_na=False)
            df.to_sql(name, con, if_exists="replace", index=False)
        con.executescript(APP_SCHEMA)
        con.commit()
    finally:
        con.close()


@lru_cache
def _connection() -> sqlite3.Connection:
    build_db()
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def connect() -> sqlite3.Connection:
    """Process-wide connection (SQLite handles our tiny concurrency fine with WAL)."""
    return _connection()
