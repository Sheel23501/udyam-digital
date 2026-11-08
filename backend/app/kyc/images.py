"""Image-level KYC: gates -> extraction -> text-level evaluate(). Entry point for the API, the report script and the UI."""
from .extract import extract
from .gates import gate
from .pipeline import evaluate
from .schemas import DOC_TYPES, CheckResult, KycReport

HEADER_KEYWORDS = {
    "gst_certificate": ("gst",),
    "udyam_certificate": ("udyam",),
    "signatory_id": ("signatory", "identity", " id"),
    "address_proof": ("electricity", "bill", "utility"),
}


def _doc_type_ok(doc_type: str, header_text: str) -> bool:
    h = f" {(header_text or '').lower()}"
    return any(k in h for k in HEADER_KEYWORDS[doc_type])


def run_images(applicant: str, files: dict[str, str], udyam_only_path: bool = False, use_cache: bool = True) -> KycReport:
    """files: {doc_type: image path}. Missing keys are reported by the completeness check."""
    flags: list[CheckResult] = []
    docs: dict[str, object | None] = {t: None for t in DOC_TYPES}
    for doc_type, path in files.items():
        if doc_type not in DOC_TYPES:
            continue
        try:
            flag, _ = gate(path, doc_type)
        except ValueError:                                   # not decodable as an image
            flags.append(CheckResult(
                code="IMAGE_UNREADABLE", status="REVIEW", evidence=doc_type,
                message_en=f"We could not open the {doc_type.replace('_', ' ')} photo. Please upload a clear PNG or JPG photo.",
                message_hi="दस्तावेज़ की फ़ोटो खुल नहीं सकी। कृपया साफ़ PNG या JPG फ़ोटो दें।"))
            continue
        if flag:
            flags.append(flag)
            continue                                   # do not spend an extraction call on an unreadable photo
        doc = extract(path, doc_type, use_cache=use_cache)
        if not _doc_type_ok(doc_type, getattr(doc, "header_text", "")):
            flags.append(CheckResult(
                code="DOC_TYPE_MISMATCH", status="REVIEW", evidence=f"{doc_type}: header='{getattr(doc, 'header_text', '')}'",
                message_en=f"The file uploaded as {doc_type.replace('_', ' ')} looks like a different document. Please upload the right one.",
                message_hi="अपलोड किया गया दस्तावेज़ सही प्रकार का नहीं लगता। कृपया सही दस्तावेज़ दें।"))
            continue
        docs[doc_type] = doc
    return evaluate(
        applicant,
        docs["gst_certificate"], docs["udyam_certificate"], docs["signatory_id"], docs["address_proof"],
        image_flags=flags, udyam_only_path=udyam_only_path, uploaded=set(files) & set(DOC_TYPES),
    )
