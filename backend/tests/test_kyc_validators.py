import json
from pathlib import Path

import pytest

from app.data.loader import connect
from app.kyc.checksum import checksum_ok, format_ok, is_valid
from app.kyc.normalise import normalise_gstin, normalise_name, normalise_udyam, pin_code
from app.kyc.pipeline import evaluate_fields
from app.kyc.report import mask_gstin, mask_udyam

HERE = Path(__file__).parent
KEY = json.loads((HERE / "kyc_answer_key.json").read_text(encoding="utf-8"))
APPLICANTS = [k for k in KEY if k.startswith("K")]


# ---------- checksum ----------
def test_checksum_validates_entire_registry():
    rows = connect().execute("SELECT gstin FROM mock_gstin_registry").fetchall()
    assert rows and all(is_valid(r["gstin"]) for r in rows)


@pytest.mark.parametrize("bad", ["08YKZXS8189L1ZO", "27PZSXS1936D1ZH", "37IHKXV5167L1ZX", "", "ABC", "27XUIXG0767D1Z"])
def test_checksum_rejects(bad):
    assert not checksum_ok(bad)


def test_format_accepts_x_pan_entity():
    assert format_ok("32TTNXB7384T1ZW") and not format_ok("32ttnxb7384t1zw") and not format_ok("32TTNXB7384T1AW")


# ---------- normalisation ----------
def test_normalise_fixes_confusables_by_position_only():
    assert normalise_gstin("19E0GXH4115Y1ZL") == "19EOGXH4115Y1ZL"       # 0 -> O in a letter slot
    assert normalise_gstin("O8YKZXS5189L1ZO") == "08YKZXS5189L1ZO"       # O -> 0 in a digit slot, last char untouched
    assert normalise_gstin("27 XUIX G0767 D1ZP") == "27XUIXG0767D1ZP"
    assert normalise_gstin("08YKZXS8189L1ZO") == "08YKZXS8189L1ZO"       # a tampered digit is NOT corrected
    assert normalise_gstin("24X0RXG9365M1Z3") == "24XORXG9365M1Z3"       # K08 as Gemini read it
    assert normalise_gstin("08YKZXS5189L1Z0") == "08YKZXS5189L1ZO"       # check char read as 0: checksum says O
    assert normalise_gstin("08YKZXS8189L1Z0") == "08YKZXS8189L1Z0"       # tampered digit AND misread check char: still invalid


def test_normalise_udyam_and_pin():
    assert normalise_udyam("UDYAM - MH - 00 - 9516696") == "UDYAM-MH-00-9516696"
    assert normalise_udyam("UNREADABLE") == "UNREADABLE"
    assert pin_code("Shop/Unit 4, Lake View Colony, Chennai, Tamil Nadu - 304733") == "304733"
    assert pin_code("Kochi, Kerala - 75 / 2083") == "752083"
    assert normalise_name("Saffron Dental Care LLP") == normalise_name("Saffron Dental Care")


def test_masking():
    assert mask_gstin("27XUIXG0767D1ZP") == "27XXXXXXXXXX1ZP"
    assert mask_udyam("UDYAM-MH-00-9516696") == "UDYAM-MH-00-XXXX696"


# ---------- the 12 applicants vs the answer key ----------
@pytest.mark.parametrize("app", APPLICANTS)
def test_applicant_matches_answer_key(app):
    fields = json.loads((HERE / "kyc_fields" / f"{app}.json").read_text(encoding="utf-8"))
    report = evaluate_fields(app, fields)
    failing = {c.code for c in report.checks if c.status in ("FAIL", "REVIEW")}
    expected = KEY[app]
    assert report.verdict == expected["verdict"], f"{app}: {report.verdict} != {expected['verdict']}; failing={failing}"
    assert set(expected["codes"]) <= failing, f"{app}: expected codes {expected['codes']} not all in {failing}"
    if expected["verdict"] == "PASS":
        assert not failing
    for c in report.checks:                              # every check has human sentences in both languages
        assert c.message_en and c.message_hi
    assert report.masked.get("gstin", "X").count("X") >= 10


def test_k06_report_surfaces_tampering_evidence():
    fields = json.loads((HERE / "kyc_fields" / "K06.json").read_text(encoding="utf-8"))
    report = evaluate_fields("K06", fields)
    nir = next(c for c in report.checks if c.code == "GSTIN_NOT_IN_REGISTRY")
    assert "08YKZXS5189L1ZO" in nir.evidence and "altered" in nir.message_en


def test_k11_message_names_the_cutoff_date():
    fields = json.loads((HERE / "kyc_fields" / "K11.json").read_text(encoding="utf-8"))
    stale = next(c for c in evaluate_fields("K11", fields).checks if c.code == "ADDRESS_PROOF_STALE")
    assert "257 days" in stale.evidence and "16 April 2026" in stale.message_en


def test_k10_names_both_people():
    fields = json.loads((HERE / "kyc_fields" / "K10.json").read_text(encoding="utf-8"))
    sig = next(c for c in evaluate_fields("K10", fields).checks if c.code == "SIGNATORY_NOT_AUTHORISED")
    assert "Nisha Arora" in sig.message_en and "Fatima Menon" in sig.message_en
