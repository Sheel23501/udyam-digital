"""Smart KYC: upload documents, run the checks (own uploads or a sample applicant), fetch a report."""
import glob
import io
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel, Field

from .. import config
from ..advisor import sessions
from ..kyc.images import run_images
from ..kyc.schemas import DOC_TYPES
from ..data.loader import connect
from ..privacy import audit
from .consent import require_consent

router = APIRouter(tags=["kyc"])

MAX_BYTES = 8 * 1024 * 1024
ALLOWED_EXT = {".png", ".jpg", ".jpeg"}
SAMPLE_DIR = Path(config.DATA_DIR) / "kyc_documents"


class RunIn(BaseModel):
    session_id: str = Field(..., description="a session with an active consent (403 otherwise)")
    sample_applicant: str | None = Field(None, description="K01..K12 to run one of the provided sample packs instead of this session's uploads")
    udyam_only: bool = Field(False, description="owner has no GST: verify on the Udyam path")


def sample_files(applicant: str) -> dict[str, str]:
    files = {}
    for p in glob.glob(str(SAMPLE_DIR / f"{applicant}_*.png")) + glob.glob(str(SAMPLE_DIR / f"{applicant}_*.jpg")):
        doc_type = Path(p).stem.split("_", 1)[1]
        if doc_type in DOC_TYPES:
            files[doc_type] = p
    return files


def session_files(session_id: str) -> dict[str, str]:
    folder = Path(config.UPLOAD_DIR) / session_id
    files = {}
    if folder.exists():
        for p in folder.iterdir():
            if p.stem in DOC_TYPES and p.suffix.lower() in ALLOWED_EXT:
                files[p.stem] = str(p)
    return files


@router.get("/kyc/samples")
def samples() -> list[dict]:
    apps = sorted({Path(p).stem.split("_", 1)[0] for p in glob.glob(str(SAMPLE_DIR / "K*_*.png"))})
    return [{"applicant": a, "docs": sorted(sample_files(a))} for a in apps]


@router.post("/kyc/upload", status_code=201)
async def upload(session_id: str = Form(...), doc_type: str = Form(...), file: UploadFile = File(...)) -> dict:
    require_consent(session_id)
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, {"message": "unknown doc_type", "allowed": list(DOC_TYPES)})
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, {"message": "only PNG or JPG photos are accepted", "got": ext or "(none)"})
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file larger than 8 MB")
    if not data:
        raise HTTPException(400, "empty file")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
    except Exception:  # noqa: BLE001 — anything PIL cannot read is not a photo of a document
        raise HTTPException(400, {"message": "this file is not a readable PNG or JPG photo"}) from None
    folder = Path(config.UPLOAD_DIR) / session_id
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{doc_type}.*"):
        old.unlink()
    (folder / f"{doc_type}{ext}").write_bytes(data)
    audit.log("owner", "kyc.upload", f"{session_id} {doc_type}")
    return {"session_id": session_id, "doc_type": doc_type, "bytes": len(data), "uploaded": sorted(session_files(session_id))}


@router.post("/kyc/run")
def run(body: RunIn) -> dict:
    """Run every check and store the report. Requires consent. With `sample_applicant` the provided K01..K12 pack is
    used (extractions are cached in git, so this needs no vision API quota)."""
    require_consent(body.session_id)
    if body.sample_applicant:
        applicant = body.sample_applicant.upper()
        files = sample_files(applicant)
        if not files:
            raise HTTPException(404, {"message": "unknown sample applicant", "available": [s["applicant"] for s in samples()]})
    else:
        applicant = f"S-{body.session_id[:6]}"
        files = session_files(body.session_id)
        if body.udyam_only:
            files.pop("gst_certificate", None)                # the owner chose the no-GST path: ignore an earlier GST upload
        if not files:
            raise HTTPException(400, {"message": "no documents uploaded for this session", "upload": "POST /kyc/upload", "doc_types": list(DOC_TYPES)})
    try:
        report = run_images(applicant, files, udyam_only_path=body.udyam_only, use_cache=True)
    except Exception as e:  # noqa: BLE001 — the vision API can be out of quota; say so instead of a 500
        logging.getLogger(__name__).warning("kyc run failed: %s", type(e).__name__)
        raise HTTPException(503, {"message": "document reading service unavailable, please retry in a minute"}) from None
    app_id = "KYC-" + uuid.uuid4().hex[:8].upper()
    con = connect()
    con.execute("INSERT INTO kyc_applications(id, session_id, applicant, verdict, report_json, ts) VALUES (?,?,?,?,?,?)",
                (app_id, body.session_id, applicant, report.verdict, report.model_dump_json(), audit.now_iso()))
    con.commit()
    sessions.set_status(body.session_id, f"kyc_{report.verdict.lower()}")
    audit.log("system", "kyc.run", f"{body.session_id} {applicant} {report.verdict} {report.masked.get('gstin', '')}")
    return {"application_id": app_id, "session_id": body.session_id, **report.model_dump(mode="json")}


@router.get("/kyc/{application_id}")
def get_report(application_id: str) -> dict:
    row = connect().execute("SELECT * FROM kyc_applications WHERE id = ?", (application_id,)).fetchone()
    if not row:
        raise HTTPException(404, "unknown application")
    audit.log("staff", "kyc.view", f"{row['session_id']} {application_id}")
    return {"application_id": row["id"], "session_id": row["session_id"], "ts": row["ts"], **json.loads(row["report_json"])}
