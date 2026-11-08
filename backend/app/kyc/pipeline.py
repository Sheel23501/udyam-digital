"""KYC evaluation over extracted document fields (text level). Phase 4 adds image gates + Gemini extraction on top
and calls `evaluate()` with the results; tests call it directly with fixtures."""
from .normalise import normalise_gstin, normalise_udyam
from .report import mask_gstin, mask_udyam, next_step, verdict
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
) -> KycReport:
    present = {name for name, doc in (("gst_certificate", gst), ("udyam_certificate", udyam), ("signatory_id", sig), ("address_proof", bill)) if doc is not None}
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

    if bill is not None:
        checks.append(V.check_address_recency(bill))

    v = verdict(checks)
    en, hi = next_step(v, checks)
    return KycReport(applicant=applicant, verdict=v, checks=checks, masked=masked, next_step_en=en, next_step_hi=hi)


def evaluate_fields(applicant: str, fields: dict) -> KycReport:
    """Convenience for fixtures / API: fields = {"gst_certificate": {...} | None, "udyam_certificate": ..., "signatory_id": ..., "address_proof": ..., "image_flags": [...]}."""
    def mk(cls, key):
        d = fields.get(key)
        return cls(**d) if d else None
    flags = [CheckResult(**f) for f in fields.get("image_flags", [])]
    return evaluate(applicant, mk(GstCertificate, "gst_certificate"), mk(UdyamCertificate, "udyam_certificate"),
                    mk(SignatoryId, "signatory_id"), mk(ElectricityBill, "address_proof"), flags, fields.get("udyam_only_path", False))
