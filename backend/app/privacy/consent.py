"""DPDP consent: itemised purposes, recorded with timestamp, language and notice version; withdrawable.

Nothing that touches KYC documents (upload, run) is allowed without an active consent for the session."""
import json

from ..data.loader import connect
from .audit import now_iso

NOTICE_VERSION = "2026-07-v1"

PURPOSES = [
    {"id": "identity_verification", "required": True,
     "en": "Verify your business identity from the documents you upload (GST/Udyam certificate, signatory ID, address proof).",
     "hi": "आपके अपलोड किए दस्तावेज़ों (GST/उद्यम प्रमाणपत्र, हस्ताक्षरकर्ता पहचान, पता प्रमाण) से व्यवसाय की पहचान सत्यापित करना।"},
    {"id": "service_provisioning", "required": True,
     "en": "Set up and deliver the services you order (installation, SIM activation, billing).",
     "hi": "आपके द्वारा ऑर्डर की गई सेवाएँ चालू करना (इंस्टॉलेशन, SIM सक्रियण, बिलिंग)।"},
    {"id": "regulatory_kyc_record", "required": True,
     "en": "Keep the KYC record that telecom regulations require, for the period they require.",
     "hi": "दूरसंचार नियमों के अनुसार KYC रिकॉर्ड, निर्धारित अवधि तक रखना।"},
    {"id": "service_updates", "required": True,
     "en": "Send you updates about your order and service (installation date, outages) by SMS or WhatsApp.",
     "hi": "आपके ऑर्डर और सेवा से जुड़ी सूचनाएँ (इंस्टॉलेशन की तारीख, रुकावटें) SMS या WhatsApp पर भेजना।"},
    {"id": "marketing", "required": False,
     "en": "Tell you about offers and new services (optional; you can switch this off any time).",
     "hi": "ऑफ़र और नई सेवाओं की जानकारी देना (वैकल्पिक; कभी भी बंद कर सकते हैं)।"},
]
REQUIRED = frozenset(p["id"] for p in PURPOSES if p["required"])

NOTICE = {
    "en": ("Accel Business (the data fiduciary) will use the details below only for the purposes you tick. "
           "Your documents are read by an automated service to extract the fields needed for verification; "
           "identifiers are masked everywhere they are shown or logged. Rejected applications are deleted after 30 days; "
           "verified ones keep only the extracted fields for the regulatory period and the images for 90 days. "
           "You can withdraw consent from the order tracker at any time; we then stop processing and delete what the law does not require us to keep."),
    "hi": ("Accel Business (डेटा फ़िड्यूशियरी) नीचे दिए विवरण का उपयोग केवल उन्हीं उद्देश्यों के लिए करेगा जिन्हें आप चुनेंगे। "
           "आपके दस्तावेज़ एक स्वचालित सेवा द्वारा पढ़े जाते हैं ताकि सत्यापन के लिए ज़रूरी जानकारी निकाली जा सके; "
           "पहचान संख्याएँ हर जगह मास्क करके दिखाई और लॉग की जाती हैं। अस्वीकृत आवेदन 30 दिन बाद हटा दिए जाते हैं; "
           "सत्यापित आवेदनों में केवल निकाली गई जानकारी नियामक अवधि तक और छवियाँ 90 दिन तक रखी जाती हैं। "
           "आप ऑर्डर ट्रैकर से कभी भी सहमति वापस ले सकते हैं; तब हम प्रोसेसिंग रोक देते हैं और जो कानून को नहीं चाहिए उसे हटा देते हैं।"),
}


def notice(language: str = "en") -> dict:
    lang = "hi" if language == "hi" else "en"
    return {"version": NOTICE_VERSION, "language": lang, "text": NOTICE[lang],
            "purposes": [{"id": p["id"], "required": p["required"], "label": p[lang]} for p in PURPOSES]}


def missing_required(purposes: list[str]) -> list[str]:
    return sorted(REQUIRED - set(purposes))


def record(session_id: str, purposes: list[str], language: str, notice_version: str) -> dict:
    con = connect()
    ts = now_iso()
    cur = con.execute("INSERT INTO consents(session_id, purposes_json, language, notice_version, ts) VALUES (?,?,?,?,?)",
                      (session_id, json.dumps(sorted(set(purposes))), language, notice_version, ts))
    con.commit()
    return {"consent_id": int(cur.lastrowid), "session_id": session_id, "purposes": sorted(set(purposes)), "ts": ts,
            "notice_version": notice_version, "language": language}


def withdraw(consent_id: int) -> dict | None:
    con = connect()
    row = con.execute("SELECT id, session_id, withdrawn_ts FROM consents WHERE id = ?", (consent_id,)).fetchone()
    if not row:
        return None
    ts = row["withdrawn_ts"] or now_iso()
    con.execute("UPDATE consents SET withdrawn_ts = ? WHERE id = ?", (ts, consent_id))
    con.commit()
    return {"consent_id": consent_id, "session_id": row["session_id"], "withdrawn_ts": ts}


def active_for(session_id: str) -> dict | None:
    """The latest un-withdrawn consent that covers every required purpose, or None."""
    rows = connect().execute("SELECT * FROM consents WHERE session_id = ? AND withdrawn_ts IS NULL ORDER BY id DESC",
                             (session_id,)).fetchall()
    for r in rows:
        purposes = set(json.loads(r["purposes_json"]))
        if REQUIRED <= purposes:
            return {"consent_id": r["id"], "purposes": sorted(purposes), "ts": r["ts"], "language": r["language"],
                    "notice_version": r["notice_version"]}
    return None


def history(session_id: str) -> list[dict]:
    rows = connect().execute("SELECT * FROM consents WHERE session_id = ? ORDER BY id", (session_id,)).fetchall()
    return [{"consent_id": r["id"], "purposes": json.loads(r["purposes_json"]), "ts": r["ts"], "withdrawn_ts": r["withdrawn_ts"],
             "language": r["language"], "notice_version": r["notice_version"]} for r in rows]
