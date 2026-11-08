"""Udyam Digital API: the same endpoints the Streamlit UI uses, open for judges to call directly.

Typical journey:  POST /sessions -> POST /advisor/chat (×n) -> POST /engine/validate (quote edits) -> POST /consent
                  -> POST /kyc/upload (×4) or POST /kyc/run {sample_applicant} -> POST /orders -> GET /orders/{id}
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .data.loader import build_db, connect
from .engine.catalogue import catalogue
from .llm.providers import chain
from .routers import advisor, backoffice, consent, engine, kyc, lookup, orders

DESCRIPTION = """
Digital acquisition and onboarding journey for Accel Business SMB customers.

* **Rules engine decides, LLM narrates.** `POST /engine/recommend` and `POST /engine/validate` are deterministic; the
  advisor (`POST /advisor/chat`) only collects facts and explains the engine's result.
* **Consent before documents.** `POST /kyc/upload` and `POST /kyc/run` return **403** until `POST /consent` has been
  recorded for the session (DPDP Act 2023). Identifiers are masked in every response and in the audit log.
* **Sample packs.** `POST /kyc/run {"session_id": ..., "sample_applicant": "K07"}` runs one of the 12 provided
  applicants from cached extractions, so no vision API quota is needed.
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    build_db()
    connect()
    yield


app = FastAPI(title="Udyam Digital API", version="0.6.0", description=DESCRIPTION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
for r in (advisor, engine, consent, kyc, lookup, orders, backoffice):
    app.include_router(r.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    con = connect()
    return {
        "ok": True,
        "catalogue_products": len(catalogue()),
        "gstin_registry_rows": con.execute("SELECT COUNT(*) FROM mock_gstin_registry").fetchone()[0],
        "udyam_registry_rows": con.execute("SELECT COUNT(*) FROM mock_udyam_registry").fetchone()[0],
        "leads_rows": con.execute("SELECT COUNT(*) FROM smb_leads").fetchone()[0],
        "advisor_providers": [p.name for p in chain()],      # names only, never keys
    }
