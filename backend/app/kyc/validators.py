"""One validator per fault class. Each returns CheckResult(s) with a machine code, evidence and a human sentence
in English and Hindi. Validators are pure functions over extracted text; registry access goes through lookup/."""
import re
from datetime import date, timedelta

import jellyfish

from ..config import ADDRESS_PROOF_MAX_AGE_DAYS, TODAY
from ..lookup.registry import gstin_by_name, gstin_lookup, lead_contact_for, udyam_lookup
from .checksum import checksum_ok, format_ok
from .normalise import normalise_name, pin_code
from .schemas import DOC_TYPES, UNREADABLE, CheckResult, ElectricityBill, GstCertificate, SignatoryId, UdyamCertificate

GST_STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
    "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}
UDYAM_STATE_ABBR = {
    "AP": "Andhra Pradesh", "BR": "Bihar", "DL": "Delhi", "GJ": "Gujarat", "HR": "Haryana", "KA": "Karnataka",
    "KL": "Kerala", "MH": "Maharashtra", "MP": "Madhya Pradesh", "PB": "Punjab", "RJ": "Rajasthan", "TN": "Tamil Nadu",
    "TS": "Telangana", "TG": "Telangana", "UP": "Uttar Pradesh", "WB": "West Bengal", "OD": "Odisha", "JH": "Jharkhand",
    "CG": "Chhattisgarh", "UK": "Uttarakhand", "AS": "Assam", "GA": "Goa", "HP": "Himachal Pradesh",
}
PROP_RE = re.compile(r"^(?P<person>.+?)\s*\(\s*Prop\.?\s*(?P<biz>.+?)\s*\)\s*$", re.IGNORECASE)
NAME_SIMILARITY_MIN = 0.95
GSTIN_CONFIDENCE_MIN = 0.9
CUTOFF = TODAY - timedelta(days=ADDRESS_PROOF_MAX_AGE_DAYS)


def _r(code, status, evidence, en, hi) -> CheckResult:
    return CheckResult(code=code, status=status, evidence=str(evidence), message_en=en, message_hi=hi)


def _same(a: str, b: str) -> bool:
    na, nb = normalise_name(a), normalise_name(b)
    return bool(na) and bool(nb) and (na == nb or jellyfish.jaro_winkler_similarity(na, nb) >= NAME_SIMILARITY_MIN)


def proprietor(legal_name: str) -> tuple[str | None, str | None]:
    m = PROP_RE.match(legal_name or "")
    return (m.group("person").strip(), m.group("biz").strip()) if m else (None, None)


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat((s or "").strip())
    except ValueError:
        return None


# 1. completeness -------------------------------------------------------------------------------------------------
def check_completeness(present: set[str], udyam_only_path: bool = False) -> CheckResult:
    required = set(DOC_TYPES) - ({"gst_certificate"} if udyam_only_path else set())
    missing = sorted(required - present)
    pretty = ", ".join(m.replace("_", " ") for m in missing)
    hi_names = {"gst_certificate": "GST प्रमाणपत्र", "udyam_certificate": "उद्यम प्रमाणपत्र", "signatory_id": "हस्ताक्षरकर्ता की आईडी", "address_proof": "पते का प्रमाण"}
    return _r("DOC_MISSING", "FAIL" if missing else "PASS", ",".join(missing),
              f"Missing document: {pretty}. Please upload it to continue." if missing else "All required documents received.",
              f"दस्तावेज़ नहीं मिला: {', '.join(hi_names[m] for m in missing)}। कृपया अपलोड करें।" if missing else "सभी ज़रूरी दस्तावेज़ मिल गए।")


# 2. GSTIN readability / format / checksum -----------------------------------------------------------------------
def check_gstin_readable(gst: GstCertificate) -> CheckResult | None:
    if gst.gstin.upper() == UNREADABLE or gst.gstin_confidence < GSTIN_CONFIDENCE_MIN:
        return _r("GSTIN_UNREADABLE", "REVIEW", f"confidence={gst.gstin_confidence:.2f} read={gst.gstin}",
                  "We could not read the GSTIN on your certificate clearly. Please upload a sharper photo, flat and in good light.",
                  "प्रमाणपत्र पर GSTIN साफ़ नहीं पढ़ा गया। कृपया साफ़ फ़ोटो दोबारा अपलोड करें।")
    return None


def check_gstin_format(gstin: str) -> CheckResult:
    if not format_ok(gstin):
        return _r("GSTIN_FORMAT", "FAIL", gstin, "The GSTIN on the certificate is not in a valid format.", "GSTIN का प्रारूप सही नहीं है।")
    if not checksum_ok(gstin):
        return _r("GSTIN_CHECKSUM", "FAIL", gstin,
                  "The GSTIN on the certificate does not pass its check digit. Please upload the original certificate.",
                  "GSTIN का चेक अंक मेल नहीं खाता। कृपया असली प्रमाणपत्र अपलोड करें।")
    return _r("GSTIN_CHECKSUM", "PASS", gstin, "GSTIN format and check digit are valid.", "GSTIN का प्रारूप सही है।")


# 3. registry status (+ tampering evidence) -----------------------------------------------------------------------
def check_gstin_registry(gstin: str, trade_name: str) -> tuple[CheckResult, dict | None]:
    rec = gstin_lookup(gstin)
    if not rec:
        near = [r["gstin"] for r in gstin_by_name(trade_name) if len(r["gstin"]) == 15 and sum(a != b for a, b in zip(r["gstin"], gstin)) <= 2]
        extra_en = " A registration with a very similar number exists for this business name, so the certificate may have been altered." if near else ""
        return _r("GSTIN_NOT_IN_REGISTRY", "FAIL", f"near_match={near}" if near else "none",
                  "This GSTIN was not found in the GST registry." + extra_en,
                  "यह GSTIN रजिस्ट्री में नहीं मिला।" + (" इसी नाम से मिलती-जुलती संख्या मौजूद है — प्रमाणपत्र बदला गया हो सकता है।" if near else "")), None
    status = rec["status"]
    if status == "Active":
        return _r("GSTIN_STATUS", "PASS", status, "GST registration is active.", "GST पंजीकरण सक्रिय है।"), rec
    return _r("GSTIN_STATUS", "FAIL", status,
              f"GST registration is {status}. We can only onboard businesses with an active GSTIN; please reactivate it or proceed without GST products.",
              f"GST पंजीकरण {status} है। सक्रिय GSTIN के बिना हम GST वाले उत्पाद नहीं दे सकते।"), rec


# 4. state consistency ---------------------------------------------------------------------------------------------
def check_state_consistency(gst: GstCertificate, udyam: UdyamCertificate | None, reg: dict | None) -> CheckResult:
    code_state = GST_STATE_CODES.get(gst.gstin[:2])
    states = {"GSTIN code": code_state, "GST certificate": gst.state}
    if reg:
        states["Registry"] = reg["state"]
    if udyam and udyam.udyam_number.startswith("UDYAM-"):
        states["Udyam number"] = UDYAM_STATE_ABBR.get(udyam.udyam_number[6:8])
        states["Udyam certificate"] = udyam.state
    norm = {k: normalise_name(v) for k, v in states.items() if v}
    # Reference = the state implied by the GSTIN code (or the registry). Printed states may be truncated by a line
    # wrap ("Maharashtr") or abbreviated, so accept prefix matches and near-identical strings, not just equality.
    ref = norm.get("GSTIN code") or norm.get("Registry") or next(iter(norm.values()), "")

    def _state_same(a: str, b: str) -> bool:
        if not a or not b:
            return True
        if a == b or (len(min(a, b, key=len)) >= 5 and (a.startswith(b) or b.startswith(a))):
            return True
        return jellyfish.jaro_winkler_similarity(a, b) >= 0.9

    ok = all(_state_same(ref, v) for v in norm.values())
    return _r("STATE_MISMATCH", "PASS" if ok else "FAIL", "; ".join(f"{k}={v}" for k, v in states.items()),
              "State is consistent across GSTIN, certificates and registry." if ok else "The state differs between your GSTIN, certificates and the registry.",
              "राज्य सभी दस्तावेज़ों में एक जैसा है।" if ok else "राज्य दस्तावेज़ों में अलग-अलग है।")


# 5. date of liability vs registry -------------------------------------------------------------------------------
def check_date_of_liability(gst: GstCertificate, reg: dict | None) -> CheckResult | None:
    if not reg:
        return None
    ok = (gst.date_of_liability or "").strip() == (reg.get("registration_date") or "").strip()
    return _r("GST_DATE_MISMATCH", "PASS" if ok else "REVIEW", f"cert={gst.date_of_liability} registry={reg.get('registration_date')}",
              "Registration date matches the registry." if ok else "The registration date on the certificate differs from the registry; we will verify manually.",
              "पंजीकरण तिथि रजिस्ट्री से मेल खाती है।" if ok else "पंजीकरण तिथि रजिस्ट्री से अलग है; हम जांच करेंगे।")


# 6. Udyam ---------------------------------------------------------------------------------------------------------
def check_udyam(udyam: UdyamCertificate) -> list[CheckResult]:
    num = (udyam.udyam_number or "").strip().upper()
    if not num or num == UNREADABLE:
        return [_r("UDYAM_MISSING_NUMBER", "FAIL", "",
                   "The Udyam certificate has no registration number on it. Please upload a valid Udyam certificate.",
                   "उद्यम प्रमाणपत्र पर पंजीकरण संख्या नहीं है। कृपया वैध प्रमाणपत्र अपलोड करें।")]
    if not re.fullmatch(r"UDYAM-[A-Z]{2}-\d{2}-\d{7}", num):
        return [_r("UDYAM_FORMAT", "FAIL", num, "The Udyam number is not in a valid format.", "उद्यम संख्या का प्रारूप सही नहीं है।")]
    rec = udyam_lookup(num)
    if not rec:
        return [_r("UDYAM_NOT_FOUND", "FAIL", num, "This Udyam number was not found in the registry.", "यह उद्यम संख्या रजिस्ट्री में नहीं मिली।")]
    ok = _same(rec["enterprise_name"], udyam.enterprise_name)
    return [_r("UDYAM_NAME", "PASS" if ok else "FAIL", f"cert={udyam.enterprise_name} registry={rec['enterprise_name']}",
               "Udyam registration verified." if ok else "The business name on the Udyam certificate does not match the registry.",
               "उद्यम पंजीकरण सत्यापित।" if ok else "उद्यम प्रमाणपत्र पर नाम रजिस्ट्री से मेल नहीं खाता।")]


# 7. name consistency ----------------------------------------------------------------------------------------------
def check_names(gst: GstCertificate, udyam: UdyamCertificate | None, bill: ElectricityBill | None, reg: dict | None) -> CheckResult:
    ref = gst.trade_name
    _, legal_biz = proprietor(gst.legal_name)
    compare = {"GST legal name": legal_biz or gst.legal_name}
    if udyam:
        compare["Udyam certificate"] = udyam.enterprise_name
    if bill:
        compare["Electricity bill"] = bill.billed_to
    if reg:
        compare["Registry trade name"] = reg["trade_name"]
    bad = [k for k, v in compare.items() if not _same(ref, v)]
    if reg and not _same(gst.legal_name, reg["legal_name"]):
        bad.append("GST legal name vs registry")
        compare["GST legal name vs registry"] = f"{gst.legal_name} | {reg['legal_name']}"
    ok = not bad
    return _r("NAME_MISMATCH", "PASS" if ok else "FAIL", "; ".join(f"{k}: {compare[k]}" for k in bad) or f"trade_name={ref}",
              "Business name is consistent across all documents." if ok else f"The business name differs between documents ({', '.join(bad)}). Please upload documents that all carry the same registered name.",
              "व्यवसाय का नाम सभी दस्तावेज़ों में एक जैसा है।" if ok else "दस्तावेज़ों में व्यवसाय का नाम अलग-अलग है। कृपया एक ही पंजीकृत नाम वाले दस्तावेज़ दें।")


# 8. address proof recency -----------------------------------------------------------------------------------------
def check_address_recency(bill: ElectricityBill) -> CheckResult:
    d = _parse_date(bill.bill_date)
    if d is None:
        return _r("ADDRESS_PROOF_DATE", "REVIEW", bill.bill_date, "We could not read the date on your electricity bill. Please upload a clearer copy.", "बिजली बिल की तारीख पढ़ नहीं पाए। कृपया साफ़ कॉपी दें।")
    age = (TODAY - d).days
    if age < 0:
        return _r("ADDRESS_PROOF_FUTURE", "REVIEW", str(d), "The bill date is in the future; please check the document.", "बिल की तारीख भविष्य की है; कृपया जांचें।")
    ok = age <= ADDRESS_PROOF_MAX_AGE_DAYS
    return _r("ADDRESS_PROOF_STALE", "PASS" if ok else "FAIL", f"{d} ({age} days)",
              f"Address proof is {age} days old." + ("" if ok else f" We need a bill dated on or after {CUTOFF:%d %B %Y} (within the last {ADDRESS_PROOF_MAX_AGE_DAYS} days)."),
              f"पते का प्रमाण {age} दिन पुराना है।" + ("" if ok else f" कृपया {CUTOFF:%d-%m-%Y} या उसके बाद का बिल दें (पिछले {ADDRESS_PROOF_MAX_AGE_DAYS} दिनों का)।"))


# 9. address consistency -------------------------------------------------------------------------------------------
def check_address_consistency(gst: GstCertificate, bill: ElectricityBill | None, reg: dict | None) -> CheckResult | None:
    if not bill:
        return None
    pins = {"GST certificate": pin_code(gst.principal_address), "Electricity bill": pin_code(bill.supply_address)}
    if reg:
        pins["Registry"] = pin_code(reg.get("principal_place_of_business", ""))
    known = {k: v for k, v in pins.items() if v}
    if len(known) < 2:
        return None                                    # nothing to compare against (e.g. PIN lost to a line wrap); other checks cover it
    ok = len(set(known.values())) == 1
    return _r("ADDRESS_MISMATCH", "PASS" if ok else "FAIL", "; ".join(f"{k}={v}" for k, v in pins.items()),
              "Address proof matches the registered place of business." if ok else "The address on the electricity bill does not match the registered place of business.",
              "पते का प्रमाण पंजीकृत पते से मेल खाता है।" if ok else "बिजली बिल का पता पंजीकृत पते से मेल नहीं खाता।")


# 10. authorised signatory -----------------------------------------------------------------------------------------
def check_signatory(sig: SignatoryId, gst: GstCertificate, reg: dict | None, udyam_number: str | None = None,
                    gstin_usable: bool = True) -> list[CheckResult]:
    out: list[CheckResult] = []
    person, _ = proprietor(gst.legal_name)
    source = "the GST certificate"
    if not person:                                       # LLP / Pvt Ltd: the person of record comes from our CRM
        lead = lead_contact_for(gstin=gst.gstin if gstin_usable else None, udyam=udyam_number)
        person = lead["contact_name"] if lead else None
        source = "our records"
    if not person:
        out.append(_r("SIGNATORY_UNVERIFIED", "REVIEW", f"id={sig.name}; no person of record found",
                      "We could not confirm who is authorised to sign for this business yet; we will verify once the GST certificate is readable.",
                      "अभी यह पुष्टि नहीं हो सकी कि कौन हस्ताक्षर के लिए अधिकृत है; GST प्रमाणपत्र पढ़ने के बाद जांच करेंगे।"))
    else:
        ok = _same(sig.name, person)
        out.append(_r("SIGNATORY_NOT_AUTHORISED", "PASS" if ok else "FAIL", f"id={sig.name}; record={person} ({source})",
                      "The signatory matches the person of record for this business." if ok else
                      f"The ID is for {sig.name}, but {source} name {person} for this business. Please upload the correct ID or an authorisation letter.",
                      "हस्ताक्षरकर्ता रिकॉर्ड से मेल खाता है।" if ok else f"आईडी {sig.name} की है, जबकि रिकॉर्ड में {person} है। कृपया सही आईडी या अधिकार-पत्र दें।"))
    vt = _parse_date(sig.valid_till)
    if vt and vt < TODAY:
        out.append(_r("SIGNATORY_ID_EXPIRED", "FAIL", sig.valid_till, "The signatory ID has expired.", "आईडी की वैधता समाप्त हो गई है।"))
    const = ((reg or {}).get("constitution") or gst.constitution or "").lower()
    d = (sig.designation or "").lower()
    soft = (("proprietor" in const and d not in ("owner", "proprietor", "proprietress"))
            or ("llp" in const and "partner" not in d)
            or ("private" in const and d not in ("director", "authorised signatory", "authorized signatory")))
    if soft:
        out.append(_r("DESIGNATION_UNUSUAL", "WARN", f"{sig.designation} on {reg['constitution'] if reg else gst.constitution}",
                      f"'{sig.designation}' is an unusual designation for a {reg['constitution'] if reg else gst.constitution}; we will confirm at activation.",
                      "पदनाम इस प्रकार के व्यवसाय के लिए असामान्य है; सक्रियण पर पुष्टि करेंगे।"))
    return out


# 11. soft: PAN 5th character = first letter of trade name --------------------------------------------------------
def check_pan_initial(gst: GstCertificate) -> CheckResult | None:
    if len(gst.gstin) != 15 or not gst.trade_name:
        return None
    ok = gst.gstin[6] == gst.trade_name.strip()[0].upper()
    return None if ok else _r("PAN_INITIAL", "WARN", f"PAN 5th char {gst.gstin[6]} vs trade name {gst.trade_name}",
                              "The PAN embedded in the GSTIN does not start with the business name's initial; we will double-check.",
                              "GSTIN में PAN का अक्षर व्यवसाय के नाम से मेल नहीं खाता; हम जांच करेंगे।")
