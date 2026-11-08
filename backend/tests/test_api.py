"""API tests through FastAPI's TestClient. No network: the advisor runs in offline mode and KYC uses the cached
sample extractions. Writes go to the real SQLite file (gitignored) under unique ids; uploads go to a temp folder."""
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.data.loader import connect
from app.main import app
from app.privacy import retention

import os

os.environ.setdefault("STAFF_PIN", "test-pin-4821")
STAFF = {"X-Staff-Pin": os.environ["STAFF_PIN"]}
client = TestClient(app)
DOCS = Path(config.DATA_DIR) / "kyc_documents"
ALL_REQUIRED = ["identity_verification", "service_provisioning", "regulatory_kyc_record", "service_updates"]


@pytest.fixture(autouse=True)
def _offline_and_tmp_uploads(monkeypatch, tmp_path):
    monkeypatch.setenv("ADVISOR_OFFLINE", "1")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    yield


def new_session(language="en", **kw) -> str:
    r = client.post("/sessions", json={"language": language, **kw})
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


def consent_for(sid: str, purposes=None) -> int:
    r = client.post("/consent", json={"session_id": sid, "purposes": purposes or ALL_REQUIRED, "language": "en"})
    assert r.status_code == 201, r.text
    return r.json()["consent_id"]


def chat(sid: str, text: str) -> dict:
    r = client.post("/advisor/chat", json={"session_id": sid, "text": text})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- meta / engine ----------
def test_health_reports_data_and_providers_without_keys():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["catalogue_products"] == 25 and body["gstin_registry_rows"] > 3000
    assert all(isinstance(p, str) and len(p) < 20 for p in body["advisor_providers"])      # names only


def test_phase6_checkpoint_recommend_excludes_whatsapp_without_gst():
    r = client.post("/engine/recommend", json={"business_type": "Kirana", "employee_count": 2, "num_sites": 1, "city": "Lucknow",
                                               "has_gstin": False, "needs": ["whatsapp_customers"]})
    assert r.status_code == 200, r.text
    b = r.json()
    ids = {i["product_id"] for i in b["items"]}
    assert "P18" in ids and ids & {"P01", "P04"} and "P15" not in ids
    assert [(e["product_id"], e["reason"]) for e in b["excluded"]] == [("P15", "GSTIN_REQUIRED")]
    assert b["card"]["monthly_from"] == b["monthly_min"] > 0
    assert "₹" in b["explanation"]["hi"] and "Website + Domain Starter" in b["explanation"]["en"]


def test_validate_reports_violations_price_and_addable():
    prof = {"business_type": "Tailoring shop", "employee_count": 6, "num_sites": 1, "city": "Delhi", "has_gstin": True}
    r = client.post("/engine/validate", json={"profile": prof, "items": {"P04": 1, "P21": 1, "P99": 1}})
    assert r.status_code == 200, r.text
    v = r.json()
    reasons = {x["product_id"]: x["reason"] for x in v["violations"]}
    assert reasons == {"P21": "MIN_EMPLOYEES", "P99": "UNKNOWN_PRODUCT"}
    assert v["price"]["monthly_min"] > 0 and v["segment"] == "micro"
    addable = {a["id"]: a for a in v["addable"]}
    assert addable["P23"]["eligible"] is True                       # CCTV may ride on AirFiber
    assert addable["P09"]["eligible"] is False and addable["P09"]["reason"] == "NEEDS_BASE_LINE"


def test_catalogue_lists_all_products_with_rules():
    r = client.get("/catalogue")
    assert r.status_code == 200 and len(r.json()) == 25
    p10 = next(p for p in r.json() if p["id"] == "P10")
    assert p10["min_sites"] == 3 and p10["requires_gstin"] is True and "P01" in p10["requires_one_of"]


# ---------- sessions + advisor ----------
def test_session_chat_reaches_a_quote_and_persists():
    sid = new_session("en", partner_code="ABC123")
    assert client.get(f"/sessions/{sid}").json()["status"] == "open"
    first = chat(sid, "I run a kirana store in Lucknow, 2 people, one shop, no GST")
    assert first["recommendation"] is None and first["missing"] == ["needs"] and first["language"] == "en"
    second = chat(sid, "Customers message me on WhatsApp for orders")
    rec = second["recommendation"]
    assert rec and {b["id"] for b in rec["bundle"]} >= {"P18", "P07"} and rec["excluded"][0]["id"] == "P15"
    assert "₹" in second["text"] and second["explanation"]["hi"]
    s = client.get(f"/sessions/{sid}").json()
    assert s["status"] == "quoted" and s["recommendation"]["monthly_min"] == rec["monthly_from"] and s["partner_code"] == "ABC123"
    # a fresh process must be able to continue the conversation from the persisted JSON
    from app.advisor import sessions as store
    store._STATES.pop(sid, None)
    third = chat(sid, "Actually I have another shop too")
    assert third["profile"]["num_sites"] == 2 and third["recommendation"]["bundle"]


def test_chat_unknown_session_is_404_and_hindi_is_detected():
    assert client.post("/advisor/chat", json={"session_id": "nope", "text": "hi"}).status_code == 404
    sid = new_session("hi")
    out = chat(sid, "मेरी साड़ी की दुकान है दिल्ली में")
    assert out["language"] == "hi" and out["profile"]["city"] == "Delhi"


# ---------- consent ----------
def test_consent_notice_is_itemised_in_both_languages():
    en, hi = client.get("/consent/notice?lang=en").json(), client.get("/consent/notice?lang=hi").json()
    assert {p["id"] for p in en["purposes"]} == {p["id"] for p in hi["purposes"]}
    assert sum(p["required"] for p in en["purposes"]) == 4 and any(not p["required"] for p in en["purposes"])
    assert "DPDP" not in hi["text"] and "सहमति" in hi["text"]


def test_consent_requires_all_required_purposes_and_can_be_withdrawn():
    sid = new_session()
    r = client.post("/consent", json={"session_id": sid, "purposes": ["identity_verification"], "language": "en"})
    assert r.status_code == 400 and "service_provisioning" in r.json()["detail"]["missing"]
    assert client.post("/consent", json={"session_id": "nope", "purposes": ALL_REQUIRED}).status_code == 404
    cid = consent_for(sid, ALL_REQUIRED + ["marketing"])
    status = client.get(f"/consent/{sid}").json()
    assert status["active"]["consent_id"] == cid and "marketing" in status["active"]["purposes"]
    assert client.get(f"/sessions/{sid}").json()["status"] == "consented"
    assert client.delete(f"/consent/{sid}/{cid}").status_code == 200
    assert client.get(f"/consent/{sid}").json()["active"] is None


# ---------- KYC ----------
def test_kyc_run_refuses_without_consent_then_passes_sample_k03():
    sid = new_session()
    r = client.post("/kyc/run", json={"session_id": sid, "sample_applicant": "K03"})
    assert r.status_code == 403 and "consent" in r.json()["detail"]["message"]
    consent_for(sid)
    r = client.post("/kyc/run", json={"session_id": sid, "sample_applicant": "K03"})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["verdict"] == "PASS" and rep["application_id"].startswith("KYC-")
    assert rep["masked"]["gstin"].count("X") == 10 and all(c["status"] != "FAIL" for c in rep["checks"])
    s = client.get(f"/sessions/{sid}").json()
    assert s["status"] == "kyc_pass" and s["kyc_verdict"] == "PASS" and s["kyc_application_id"] == rep["application_id"]
    again = client.get(f"/kyc/{rep['application_id']}").json()
    assert again["verdict"] == "PASS" and again["session_id"] == sid


def test_kyc_sample_k11_fails_on_stale_address_proof():
    sid = new_session()
    consent_for(sid)
    rep = client.post("/kyc/run", json={"session_id": sid, "sample_applicant": "K11"}).json()
    assert rep["verdict"] == "FAIL"
    assert "ADDRESS_PROOF_STALE" in {c["code"] for c in rep["checks"] if c["status"] == "FAIL"}
    assert client.get(f"/sessions/{sid}").json()["status"] == "kyc_fail"


def test_kyc_samples_lists_twelve_applicants():
    s = client.get("/kyc/samples").json()
    assert [x["applicant"] for x in s] == [f"K{i:02d}" for i in range(1, 13)]
    assert "gst_certificate" in next(x for x in s if x["applicant"] == "K03")["docs"]


def test_kyc_upload_requires_consent_validates_and_stores(tmp_path):
    sid = new_session()
    png = (DOCS / "K03_gst_certificate.png").read_bytes()
    files = {"file": ("gst.png", io.BytesIO(png), "image/png")}
    r = client.post("/kyc/upload", data={"session_id": sid, "doc_type": "gst_certificate"}, files=files)
    assert r.status_code == 403
    consent_for(sid)
    r = client.post("/kyc/upload", data={"session_id": sid, "doc_type": "passport"}, files={"file": ("x.png", io.BytesIO(png), "image/png")})
    assert r.status_code == 400
    r = client.post("/kyc/upload", data={"session_id": sid, "doc_type": "gst_certificate"}, files={"file": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")})
    assert r.status_code == 400
    r = client.post("/kyc/upload", data={"session_id": sid, "doc_type": "gst_certificate"}, files={"file": ("gst.png", io.BytesIO(png), "image/png")})
    assert r.status_code == 201 and r.json()["uploaded"] == ["gst_certificate"]
    assert (Path(config.UPLOAD_DIR) / sid / "gst_certificate.png").read_bytes() == png
    r = client.post("/kyc/run", json={"session_id": new_session(), "sample_applicant": None})
    assert r.status_code == 403                                     # no consent on that other session


def test_kyc_run_with_own_uploads_uses_cached_extraction_for_known_images():
    """K03's four images uploaded as the owner's own documents: the sha256 cache means no API call."""
    sid = new_session()
    consent_for(sid)
    for doc in ("gst_certificate", "udyam_certificate", "signatory_id", "address_proof"):
        png = (DOCS / f"K03_{doc}.png").read_bytes()
        assert client.post("/kyc/upload", data={"session_id": sid, "doc_type": doc}, files={"file": (f"{doc}.png", io.BytesIO(png), "image/png")}).status_code == 201
    r = client.post("/kyc/run", json={"session_id": sid})
    assert r.status_code == 200, r.text
    assert r.json()["verdict"] == "PASS" and r.json()["applicant"].startswith("S-")


# ---------- lookup ----------
def test_lookup_masks_identifiers_and_audits():
    r = client.get("/lookup/gstin/32HJJXE5083Y1ZR")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] and body["status"] == "Cancelled" and body["gstin_masked"] == "32XXXXXXXXXX1ZR"
    assert "32HJJXE5083Y1ZR" not in r.text and body["legal_name_masked"].startswith("Neha ")
    assert client.get("/lookup/gstin/not-a-gstin").status_code == 400
    bad = client.get("/lookup/gstin/32HJJXE5083Y1ZX").json()
    assert bad["found"] is False and bad["checksum_ok"] is False
    last = client.get("/backoffice/audit?limit=5", headers=STAFF).json()
    assert any(a["action"] == "lookup.gstin" and "32XXXXXXXXXX1ZR" in a["subject_masked"] for a in last)
    assert not any("32HJJXE5083Y1ZR" in (a["subject_masked"] or "") for a in client.get("/backoffice/audit?limit=200", headers=STAFF).json())


def test_lookup_udyam():
    row = connect().execute("SELECT udyam_number FROM mock_udyam_registry LIMIT 1").fetchone()
    r = client.get(f"/lookup/udyam/{row['udyam_number']}")
    assert r.status_code == 200 and r.json()["found"] and "XXXX" in r.json()["udyam_masked"]
    assert client.get("/lookup/udyam/UDYAM-XX-00-0000000").json()["found"] is False
    assert client.get("/lookup/udyam/garbage").status_code == 400


def test_lookup_rate_limit(monkeypatch):
    from app.routers import lookup as lk
    monkeypatch.setattr(lk, "RATE_LIMIT", 3)
    lk._hits.clear()
    codes = [client.get("/lookup/gstin/32HJJXE5083Y1ZR").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    lk._hits.clear()


# ---------- orders ----------
def _session_with_quote_and_pass_kyc() -> str:
    sid = new_session()
    chat(sid, "Pharmacy in Noida, 3 staff, one shop, GST registered, I want CCTV cameras")
    consent_for(sid)
    assert client.post("/kyc/run", json={"session_id": sid, "sample_applicant": "K03"}).json()["verdict"] == "PASS"
    return sid


def test_order_requires_kyc_pass_then_tracks_stages():
    sid = new_session()
    chat(sid, "Pharmacy in Noida, 3 staff, one shop, GST registered, I want CCTV cameras")
    r = client.post("/orders", json={"session_id": sid})
    assert r.status_code == 403 and "consent" in r.json()["detail"]["message"]        # no consent yet
    consent_for(sid)
    r = client.post("/orders", json={"session_id": sid})
    assert r.status_code == 409 and "KYC" in r.json()["detail"]["message"]
    sid = _session_with_quote_and_pass_kyc()
    r = client.post("/orders", json={"session_id": sid})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["status"] == "PLACED" and o["stage_index"] == 0 and {i["product_id"] for i in o["bundle"]["items"]} >= {"P23", "P01"}
    created = datetime.fromisoformat(o["created"]).date()
    assert o["eta"]["INSTALLED"] == (created + timedelta(days=o["bundle"]["install_days"])).isoformat()
    assert client.get(f"/sessions/{sid}").json()["status"] == "ordered"
    assert client.post("/orders", json={"session_id": sid}).status_code == 409        # one order per session
    adv = client.post(f"/orders/{o['order_id']}/advance").json()
    assert adv["status"] == "VERIFIED" and adv["progress"] > 0
    assert client.get(f"/sessions/{sid}/order").json()["order_id"] == o["order_id"]
    assert client.get("/orders/ORD-NOPE").status_code == 404


def test_order_with_edited_items_is_validated():
    sid = _session_with_quote_and_pass_kyc()
    r = client.post("/orders", json={"session_id": sid, "items": {"P01": 1, "P21": 1}})
    assert r.status_code == 400 and r.json()["detail"]["violations"][0]["reason"] == "MIN_EMPLOYEES"
    r = client.post("/orders", json={"session_id": sid, "items": {"P01": 1, "P23": 4}})
    assert r.status_code == 201 and r.json()["bundle"]["monthly_min"] == 999 + 4 * 199


# ---------- back-office ----------
def test_backoffice_queue_mixes_sessions_and_sample_leads_with_scores():
    sid = new_session("hi", partner_code="P-77")
    chat(sid, "मेरी साड़ी की दुकान है दिल्ली में")
    r = client.post("/backoffice/handoff", json={"session_id": sid, "reason": "wants to talk to a person"})
    assert r.status_code == 201
    rows = client.get("/backoffice/leads?limit=300", headers=STAFF).json()
    mine = next(x for x in rows if x["id"] == sid)
    assert mine["source"] == "session" and mine["last_step"] == "handoff" and mine["partner"] == "P-77" and mine["score"] >= 0.6
    sample = [x for x in rows if x["source"] == "lead"]
    assert sample and all(0 <= x["score"] <= 1 and x["suggested_action"] and x["est_monthly_value"] >= 0 for x in sample)
    assert rows == sorted(rows, key=lambda x: (-x["score"], -x["est_monthly_value"]))
    d = client.get(f"/backoffice/leads/{sample[0]['id']}/score", headers=STAFF).json()
    assert d["score"] == sample[0]["score"] and 3 <= len(d["reasons"]) <= 4
    assert client.get(f"/backoffice/leads/{sid}/score", headers=STAFF).json()["suggested_action"].startswith("Owner asked")
    assert client.get("/backoffice/leads/L99999/score", headers=STAFF).status_code == 404


def test_scoring_prefers_recoverable_drops():
    from app.backoffice.leads import heuristic_score, score_lead
    easy = {"drop_reason": "Quote took too long to arrive", "stage_reached": "Quote accepted", "has_gstin": "Y", "monthly_telecom_spend_inr": "4000",
            "segment": "Professional offices", "lead_source": "Website form", "city_tier": "1"}
    hard = {"drop_reason": "Wrong or invalid number", "stage_reached": "Lead", "has_gstin": "N", "monthly_telecom_spend_inr": "",
            "segment": "Micro retail & services", "lead_source": "WhatsApp campaign", "city_tier": "2"}
    h_easy, h_hard = heuristic_score(easy), heuristic_score(hard)
    assert h_easy["score"] > 0.7 > 0.3 > h_hard["score"] and "one-number quote" in h_easy["suggested_action"]
    assert score_lead(easy)["score"] > score_lead(hard)["score"]


# ---------- retention / erasure ----------
def test_retention_purges_old_rejected_uploads_but_keeps_recent_and_verified():
    root = Path(config.UPLOAD_DIR)
    con = connect()
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(timespec="seconds")
    fresh = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cases = {"old_fail": ("FAIL", old), "fresh_fail": ("FAIL", fresh), "old_pass": ("PASS", old), "no_app": (None, None)}
    sids = {}
    for name, (verdict, ts) in cases.items():
        sid = new_session()
        sids[name] = sid
        (root / sid).mkdir(parents=True)
        (root / sid / "gst_certificate.png").write_bytes(b"x" * 10)
        if verdict:
            con.execute("INSERT INTO kyc_applications(id, session_id, applicant, verdict, report_json, ts) VALUES (?,?,?,?,?,?)",
                        (f"KYC-T{sid[:6]}", sid, "T", verdict, "{}", ts))
        else:
            con.execute("UPDATE sessions SET created = ? WHERE id = ?", (old, sid))
    con.commit()
    r = client.post("/admin/retention/run", json={}, headers=STAFF)
    assert r.status_code == 200
    removed = {x["session_id"] for x in r.json()["removed"]}
    assert sids["old_fail"][:6] + "…" in removed and sids["no_app"][:6] + "…" in removed
    assert not (root / sids["old_fail"]).exists() and (root / sids["fresh_fail"]).exists() and (root / sids["old_pass"]).exists()
    r = client.post("/admin/retention/run", json={"verified_days": 30}, headers=STAFF)
    assert not (root / sids["old_pass"]).exists()


def test_erasure_deletes_images_and_transcript_keeps_kyc_record():
    sid = new_session()
    chat(sid, "Bakery in Surat, 5 staff, one shop, GST registered")
    consent_for(sid)
    (Path(config.UPLOAD_DIR) / sid).mkdir(parents=True)
    (Path(config.UPLOAD_DIR) / sid / "address_proof.jpg").write_bytes(b"img")
    rep = client.post("/kyc/run", json={"session_id": sid, "sample_applicant": "K03"}).json()
    r = client.post(f"/admin/erase/{sid}", headers=STAFF)
    assert r.status_code == 200 and r.json()["images_deleted"] == 1 and r.json()["kyc_record_kept"]
    assert not (Path(config.UPLOAD_DIR) / sid).exists()
    s = client.get(f"/sessions/{sid}").json()
    assert s["status"] == "erased" and s["profile"] is None
    assert client.get(f"/kyc/{rep['application_id']}").status_code == 200
    assert client.post("/advisor/chat", json={"session_id": sid, "text": "hello"}).status_code == 410


def test_audit_log_never_contains_raw_identifiers():
    rows = client.get("/backoffice/audit?limit=500", headers=STAFF).json()
    import re
    raw_gstin = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
    assert rows and not any(raw_gstin.search(r["subject_masked"] or "") for r in rows)



# ---------- audit findings (fixed) ----------
def test_backoffice_and_admin_need_the_staff_pin():
    sid = new_session()
    for method, path in (("get", "/backoffice/leads"), ("get", "/backoffice/audit"), ("get", "/backoffice/leads/L00001/score"),
                         ("post", "/admin/retention/run"), ("post", f"/admin/erase/{sid}")):
        r = getattr(client, method)(path, **({"json": {}} if method == "post" and "retention" in path else {}))
        assert r.status_code == 401, (path, r.status_code)
        r = getattr(client, method)(path, headers={"X-Staff-Pin": "wrong"}, **({"json": {}} if "retention" in path else {}))
        assert r.status_code == 401, (path, r.status_code)
    assert client.get("/backoffice/leads?limit=1", headers=STAFF).status_code == 200


def test_backoffice_locked_when_no_staff_pin_is_configured(monkeypatch):
    monkeypatch.delenv("STAFF_PIN", raising=False)
    assert client.get("/backoffice/leads", headers={"X-Staff-Pin": ""}).status_code == 403


def test_consent_can_only_be_withdrawn_by_its_own_session():
    a, b = new_session(), new_session()
    ca, cb = consent_for(a), consent_for(b)
    assert client.delete(f"/consent/{a}/{cb}").status_code == 404                     # a cannot withdraw b's consent
    assert client.get(f"/consent/{b}").json()["active"] is not None
    assert client.delete(f"/consent/{a}/{2**63}").status_code == 422                  # out of range: validation, not a 500


def test_withdrawal_stops_orders_and_deletes_images_and_transcript():
    sid = _session_with_quote_and_pass_kyc()
    (Path(config.UPLOAD_DIR) / sid).mkdir(parents=True, exist_ok=True)
    (Path(config.UPLOAD_DIR) / sid / "gst_certificate.png").write_bytes(b"img")
    cid = client.get(f"/consent/{sid}").json()["active"]["consent_id"]
    r = client.delete(f"/consent/{sid}/{cid}")
    assert r.status_code == 200 and r.json()["cleanup"]["images_deleted"] == 1
    assert not (Path(config.UPLOAD_DIR) / sid).exists()
    assert client.post("/orders", json={"session_id": sid}).status_code == 403
    raw = connect().execute("SELECT history_json FROM sessions WHERE id = ?", (sid,)).fetchone()[0]
    assert raw is None


def test_erasure_is_final():
    sid = new_session()
    chat(sid, "I run a kirana shop in Lucknow, 2 people, one shop, no GST, customers order on WhatsApp")
    consent_for(sid)
    assert client.post(f"/admin/erase/{sid}", headers=STAFF).status_code == 200
    png = (DOCS / "K03_gst_certificate.png").read_bytes()
    assert client.post("/kyc/upload", data={"session_id": sid, "doc_type": "gst_certificate"},
                       files={"file": ("g.png", io.BytesIO(png), "image/png")}).status_code == 410
    assert client.post("/kyc/run", json={"session_id": sid, "sample_applicant": "K03"}).status_code == 410
    assert client.post("/consent", json={"session_id": sid, "purposes": ALL_REQUIRED}).status_code == 410
    assert client.post("/backoffice/handoff", json={"session_id": sid}).status_code == 410
    assert client.post("/advisor/chat", json={"session_id": sid, "text": "hello"}).status_code == 410
    row = connect().execute("SELECT status, history_json, profile_json FROM sessions WHERE id = ?", (sid,)).fetchone()
    assert tuple(row) == ("erased", None, None)


def test_kyc_after_order_does_not_reopen_the_session():
    sid = _session_with_quote_and_pass_kyc()
    assert client.post("/orders", json={"session_id": sid}).status_code == 201
    client.post("/kyc/run", json={"session_id": sid, "sample_applicant": "K11"})
    assert client.get(f"/sessions/{sid}").json()["status"] == "ordered"


def test_bad_uploads_are_rejected_cleanly():
    sid = new_session()
    consent_for(sid)
    r = client.post("/kyc/upload", data={"session_id": sid, "doc_type": "gst_certificate"},
                    files={"file": ("x.png", io.BytesIO(b"this is not an image"), "image/png")})
    assert r.status_code == 400 and "readable" in r.text
    r = client.post("/kyc/run", json={"session_id": sid, "use_cache": False, "sample_applicant": "K03"})
    assert r.status_code == 200                                                        # use_cache is ignored, never a paid call


def test_chat_and_session_never_return_a_raw_gstin():
    sid = new_session()
    out = chat(sid, "Coaching centre in Kochi, 6 staff, one centre. Our GSTIN is 32HJJXE5083Y1ZR.")
    assert out["profile"]["gstin"] == "32XXXXXXXXXX1ZR"
    assert "32HJJXE5083Y1ZR" not in json.dumps(client.get(f"/sessions/{sid}").json())


def test_engine_rejects_impossible_profiles_and_quantities():
    assert client.post("/engine/recommend", json={"employee_count": -5}).status_code == 422
    r = client.post("/engine/recommend", json={"business_type": "Clinic", "employee_count": 8, "num_sites": 1, "city": "Nagpur",
                                               "city_tier": 1, "has_gstin": True, "requested_products": ["P03"]})
    assert ("P03", "TIER_NOT_AVAILABLE") in [(e["product_id"], e["reason"]) for e in r.json()["excluded"]]   # city wins over a claimed tier
    prof = {"business_type": "Shop", "employee_count": 2, "num_sites": 1, "city": "Lucknow", "has_gstin": False}
    assert client.post("/engine/validate", json={"profile": prof, "items": {"P04": 10**400}}).status_code == 422
