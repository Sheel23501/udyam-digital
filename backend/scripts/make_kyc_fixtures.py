#!/usr/bin/env python
"""Generate text-level KYC fixtures for applicants K01-K12 into tests/kyc_fields/.

Every certificate in the sample pack reproduces its registry record exactly, except for the planted faults found
by inspecting all 47 images (see HACKATHON_WIN_PLAN.md §3.2). So each fixture = registry record + the observed
deviation. Re-run after changing the deviations table; the JSON files are committed so judges can read/edit them.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lookup.registry import gstin_lookup, udyam_lookup  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "tests" / "kyc_fields"
GST_HDR, UDY_HDR, ID_HDR, BILL_HDR = ("Specimen: GST Registration Certificate", "Specimen: Udyam Registration Certificate",
                                      "Authorised Signatory ID", "Specimen: Electricity Bill")

# applicant -> (registry GSTIN, udyam number or None, signatory name, designation, bill date, overrides)
APPLICANTS = {
    "K01": ("37IHKXV5167L1ZS", None,                  "Neha Kaur",      "Office admin", "2026-06-26", {"udyam_blank": True}),
    "K02": ("19EOGXH4115Y1ZL", "UDYAM-WB-00-5053330", "Joseph Shah",    "Manager",      "2026-05-22", {"gstin_as_read": "19E0GXH4115Y1ZL"}),
    "K03": ("27XUIXG0767D1ZP", "UDYAM-MH-00-9516696", "Joseph Singh",   "Owner",        "2026-05-30", {}),
    "K04": ("27PZSXS1936O1ZH", "UDYAM-MH-00-6131836", "Fatima Pillai",  "Partner",      "2026-05-28", {"gstin_as_read": "27PZSXS1936D1ZH", "gstin_confidence": 0.35}),
    "K05": ("32TZAXB5481U1Z1", "UDYAM-KL-00-5521886", "Anita Shah",     "Owner",        "2026-06-11", {"udyam_doc_missing": True}),
    "K06": ("08YKZXS5189L1ZO", "UDYAM-RJ-00-6577157", "Pooja Shah",     "Owner",        "2026-06-11", {"gstin_as_read": "08YKZXS8189L1ZO"}),
    "K07": ("07CPCXN0398P1ZT", "UDYAM-DL-00-9565547", "Neha Banerjee",  "Manager",      "2026-07-05", {"legal_name": "Neha Banerjee (Prop. Shri Physio Clinic)"}),
    "K08": ("24XORXG9365M1Z3", "UDYAM-GJ-00-8477445", "Joseph Rao",     "Office admin", "2026-05-26", {}),
    "K09": ("37LDYXK0296F1ZB", "UDYAM-AP-00-9751562", "Anita Kulkarni", "Office admin", "2026-07-10", {}),
    "K10": ("27QHJXK0658U1ZL", "UDYAM-MH-00-7183141", "Nisha Arora",    "Owner",        "2026-06-18", {}),
    "K11": ("03KGZXT1320R1ZZ", "UDYAM-PB-00-9719478", "Vikram Pillai",  "Owner",        "2025-10-31", {}),
    "K12": ("37NBLXS1145E1ZU", "UDYAM-AP-00-5186772", "Pooja Agarwal",  "Owner",        "2026-07-06", {}),
}


def build(app: str) -> dict:
    gstin, udyam_no, sig_name, desig, bill_date, ov = APPLICANTS[app]
    reg = gstin_lookup(gstin)
    assert reg, f"{app}: {gstin} not in registry"
    gst = {
        "header_text": GST_HDR, "gstin": ov.get("gstin_as_read", gstin), "legal_name": ov.get("legal_name", reg["legal_name"]),
        "trade_name": reg["trade_name"], "constitution": reg["constitution"], "principal_address": reg["principal_place_of_business"],
        "state": reg["state"], "date_of_liability": reg["registration_date"], "gstin_confidence": ov.get("gstin_confidence", 0.99),
    }
    udyam = None
    if not ov.get("udyam_doc_missing"):
        urec = udyam_lookup(udyam_no) if udyam_no else None
        udyam = {
            "header_text": UDY_HDR, "udyam_number": "UNREADABLE" if ov.get("udyam_blank") else udyam_no,
            "enterprise_name": (urec or {}).get("enterprise_name", reg["trade_name"]), "enterprise_type": (urec or {}).get("enterprise_type", "Micro"),
            "major_activity": (urec or {}).get("major_activity", "Services"), "state": reg["state"], "city": (urec or {}).get("city", ""),
            "date_of_registration": (urec or {}).get("date_of_registration", "UNREADABLE"),
        }
    sig = {"header_text": ID_HDR, "name": sig_name, "designation": desig, "for_business": reg["trade_name"],
           "id_number": f"SYN-ID-{abs(hash(app)) % 1_000_000:06d}", "valid_till": "2028-12-31"}
    bill = {"header_text": BILL_HDR, "consumer_number": f"EB{abs(hash(gstin)) % 10_000_000:07d}", "billed_to": reg["trade_name"],
            "supply_address": reg["principal_place_of_business"], "bill_date": bill_date, "amount": "₹ 2,340"}
    return {"applicant": app, "gst_certificate": gst, "udyam_certificate": udyam, "signatory_id": sig, "address_proof": bill}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for app in APPLICANTS:
        (OUT / f"{app}.json").write_text(json.dumps(build(app), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("wrote", app)
