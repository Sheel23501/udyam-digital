"""KYC evaluation over extracted document fields (text level). Phase 4 adds image gates + Gemini extraction on top
and calls `evaluate()` with the results; tests call it directly with fixtures."""
from .normalise import normalise_gstin, normalise_udyam
import re

from ..privacy.masking import mask_text
from .report import mask_gstin, mask_name, mask_udyam, next_step, verdict
from .schemas import CheckResult, ElectricityBill, GstCertificate, KycReport, SignatoryId, UdyamCertificate
from . import validators as V


def evaluate(
    applicant: str,
    gst: GstCertificate | None,
    udyam: UdyamCertificate | None,
    sig: SignatoryId | None,
    bill: ElectricityBill | None,
    image_flags: list[CheckResult] | None = None,
    udyam_only_path: bool = False,
    uploaded: set[str] | None = None,
) -> KycReport:
    """`uploaded` = doc types the applicant submitted (a gated/unreadable upload still counts as submitted);
    defaults to the docs for which fields are available."""
    present = uploaded if uploaded is not None else {
        name for name, doc in (("gst_certificate", gst), ("udyam_certificate", udyam), ("signatory_id", sig), ("address_proof", bill)) if doc is not None}
    checks: list[CheckResult] = [V.check_completeness(present, udyam_only_path)]
    checks += image_flags or []
    masked: dict[str, str] = {}

    reg = None
    gstin_usable = False
    if gst is not None:
        gst.gstin = normalise_gstin(gst.gstin)
        masked["gstin"] = mask_gstin(gst.gstin)
        unreadable = V.check_gstin_readable(gst)
        if unreadable:
            checks.append(unreadable)
        else:
            fmt = V.check_gstin_format(gst.gstin)
            checks.append(fmt)
            if fmt.status == "PASS":
                status_check, reg = V.check_gstin_registry(gst.gstin, gst.trade_name)
                checks.append(status_check)
                gstin_usable = True
            else:
                status_check, _ = V.check_gstin_registry(gst.gstin, gst.trade_name)   # surfaces near-match tampering evidence
                if status_check.code == "GSTIN_NOT_IN_REGISTRY":
                    checks.append(status_check)

    if udyam is not None:
        udyam.udyam_number = normalise_udyam(udyam.udyam_number)
        masked["udyam"] = mask_udyam(udyam.udyam_number)
        checks += V.check_udyam(udyam)

    if gst is not None:
        if gstin_usable:
            checks.append(V.check_state_consistency(gst, udyam, reg))
            dol = V.check_date_of_liability(gst, reg)
            if dol:
                checks.append(dol)
        checks.append(V.check_names(gst, udyam, bill, reg))
        addr = V.check_address_consistency(gst, bill, reg)
        if addr:
            checks.append(addr)
        pan = V.check_pan_initial(gst) if gstin_usable else None
        if pan:
            checks.append(pan)
        if sig is not None:
            checks += V.check_signatory(sig, gst, reg, udyam.udyam_number if udyam else None, gstin_usable)

    if gst is None and udyam is not None and udyam_only_path:
        checks.append(V.check_names_udyam(udyam, bill, sig))
        city = V.check_city_udyam(udyam, bill)
        if city:
            checks.append(city)
        if sig is not None:                                   # person of record from our records via the Udyam number
            anchor = GstCertificate(header_text="", gstin="", legal_name=udyam.enterprise_name, trade_name=udyam.enterprise_name,
                                    constitution="", principal_address="", state=udyam.state, date_of_liability="", gstin_confidence=1.0)
            checks += V.check_signatory(sig, anchor, None, udyam.udyam_number, gstin_usable=False)

    if bill is not None:
        checks.append(V.check_address_recency(bill))

    checks = _mask_checks(checks, _person_names(gst, sig, reg, udyam))
    v = verdict(checks)
    en, hi = next_step(v, checks)
    return KycReport(applicant=applicant, verdict=v, checks=checks, masked=masked, next_step_en=en, next_step_hi=hi)


def _person_names(gst, sig, reg, udyam) -> set[str]:
    """Full names of people that can appear in check evidence or messages (signatory, proprietor, person of record)."""
    names: set[str] = set()
    if sig is not None and sig.name and sig.name != "UNREADABLE":
        names.add(sig.name.strip())
    for legal in ((gst.legal_name if gst is not None else None), (reg or {}).get("legal_name")):
        person, _ = V.proprietor(legal or "")
        if person:
            names.add(person.strip())
    lead = V.lead_contact_for(gstin=gst.gstin if gst is not None else None, udyam=udyam.udyam_number if udyam is not None else None)
    if lead and lead.get("contact_name"):
        names.add(lead["contact_name"].strip())
    return {n for n in names if len(n) >= 3}


def _mask_checks(checks: list[CheckResult], names: set[str]) -> list[CheckResult]:
    """Evidence and messages leave the pipeline with GSTINs, Udyam numbers, phones and people's names masked."""
    ordered = sorted(names, key=len, reverse=True)

    def scrub(text: str) -> str:
        text = mask_text(text or "")
        for n in ordered:
            text = re.sub(re.escape(n), mask_name(n), text, flags=re.I)
        return text
    return [c.model_copy(update={"evidence": scrub(c.evidence), "message_en": scrub(c.message_en), "message_hi": scrub(c.message_hi)})
            for c in checks]


def evaluate_fields(applicant: str, fields: dict) -> KycReport:
    """Convenience for fixtures / API: fields = {"gst_certificate": {...} | None, "udyam_certificate": ..., "signatory_id": ..., "address_proof": ..., "image_flags": [...]}."""
    def mk(cls, key):
        d = fields.get(key)
        return cls(**d) if d else None
    flags = [CheckResult(**f) for f in fields.get("image_flags", [])]
    return evaluate(applicant, mk(GstCertificate, "gst_certificate"), mk(UdyamCertificate, "udyam_certificate"),
                    mk(SignatoryId, "signatory_id"), mk(ElectricityBill, "address_proof"), flags, fields.get("udyam_only_path", False))
