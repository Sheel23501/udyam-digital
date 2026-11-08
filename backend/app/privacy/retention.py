"""Retention: delete uploaded document images once they are no longer needed.

- rejected (FAIL / REVIEW) applications: images deleted RETENTION_DAYS_REJECTED days after the verdict (default 30)
- verified (PASS) applications: images deleted RETENTION_DAYS_VERIFIED days after the verdict (default 90);
  the extracted fields in the KYC report are kept for the regulatory period
- upload folders with no application at all: deleted after RETENTION_DAYS_REJECTED days
Only image files under the session's upload folder are touched. The report rows stay."""
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import config
from ..data.loader import connect

DAYS_REJECTED = int(os.getenv("RETENTION_DAYS_REJECTED", "30"))
DAYS_VERIFIED = int(os.getenv("RETENTION_DAYS_VERIFIED", "90"))


def _parse(ts: str) -> datetime:
    d = datetime.fromisoformat(ts)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _folder_size(p: Path) -> tuple[int, int]:
    files = [f for f in p.rglob("*") if f.is_file()]
    return len(files), sum(f.stat().st_size for f in files)


def purge(now: datetime | None = None, rejected_days: int | None = None, verified_days: int | None = None,
          upload_dir: Path | None = None) -> dict:
    """Delete expired upload folders. Returns what was removed and why, for the back-office screen."""
    now = now or datetime.now(timezone.utc)
    rejected_days = DAYS_REJECTED if rejected_days is None else rejected_days
    verified_days = DAYS_VERIFIED if verified_days is None else verified_days
    root = Path(upload_dir or config.UPLOAD_DIR)
    removed: list[dict] = []
    kept = 0
    if not root.exists():
        return {"removed": removed, "kept": 0, "files": 0, "bytes": 0, "rejected_days": rejected_days, "verified_days": verified_days}
    con = connect()
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        sid = folder.name
        row = con.execute("SELECT verdict, ts FROM kyc_applications WHERE session_id = ? ORDER BY ts DESC LIMIT 1", (sid,)).fetchone()
        if row:
            age_days = (now - _parse(row["ts"])).days
            limit = verified_days if row["verdict"] == "PASS" else rejected_days
            reason = f"{row['verdict']} application, {age_days} days old (limit {limit})"
        else:
            sess = con.execute("SELECT created FROM sessions WHERE id = ?", (sid,)).fetchone()
            created = _parse(sess["created"]) if sess else datetime.fromtimestamp(folder.stat().st_mtime, tz=timezone.utc)
            age_days = (now - created).days
            limit = rejected_days
            reason = f"no application, {age_days} days old (limit {limit})"
        if age_days >= limit:
            n_files, n_bytes = _folder_size(folder)
            shutil.rmtree(folder, ignore_errors=True)
            removed.append({"session_id": sid[:6] + "…", "files": n_files, "bytes": n_bytes, "reason": reason})
        else:
            kept += 1
    return {"removed": removed, "kept": kept, "files": sum(r["files"] for r in removed), "bytes": sum(r["bytes"] for r in removed),
            "rejected_days": rejected_days, "verified_days": verified_days}


def erase_session(session_id: str, upload_dir: Path | None = None) -> dict:
    """Data-principal erasure request: delete the session's images now and blank the advisor transcript.
    The KYC report row (extracted fields + verdict) is kept, as the regulatory record requires."""
    root = Path(upload_dir or config.UPLOAD_DIR) / session_id
    files = _folder_size(root)[0] if root.exists() else 0
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    con = connect()
    con.execute("UPDATE sessions SET history_json = NULL, profile_json = NULL, status = 'erased' WHERE id = ?", (session_id,))
    con.commit()
    return {"session_id": session_id[:6] + "…", "images_deleted": files, "transcript_deleted": True, "kyc_record_kept": True}
