"""Shapes for extracted KYC documents and for the validation report.

The four document models double as the Gemini `response_schema` in Phase 4, so every field is a plain string
(dates as YYYY-MM-DD, missing/unreadable values as the literal UNREADABLE) plus one confidence number.
"""
from pydantic import BaseModel, Field

UNREADABLE = "UNREADABLE"


class GstCertificate(BaseModel):
    header_text: str = Field(description="The document title as printed, e.g. 'Specimen: GST Registration Certificate'")
    gstin: str
    legal_name: str
    trade_name: str
    constitution: str
    principal_address: str
    state: str
    date_of_liability: str = Field(description="YYYY-MM-DD")
    gstin_confidence: float = Field(description="0-1: confidence that every character of the GSTIN was read correctly")


class UdyamCertificate(BaseModel):
    header_text: str
    udyam_number: str = Field(description="e.g. UDYAM-MH-00-1234567, or UNREADABLE if the field is blank")
    enterprise_name: str
    enterprise_type: str
    major_activity: str
    state: str
    city: str
    date_of_registration: str


class SignatoryId(BaseModel):
    header_text: str
    name: str
    designation: str
    for_business: str
    id_number: str
    valid_till: str = Field(description="YYYY-MM-DD")


class ElectricityBill(BaseModel):
    header_text: str
    consumer_number: str
    billed_to: str
    supply_address: str
    bill_date: str = Field(description="YYYY-MM-DD")
    amount: str


DOC_TYPES = ("gst_certificate", "udyam_certificate", "signatory_id", "address_proof")
SCHEMAS = {
    "gst_certificate": GstCertificate,
    "udyam_certificate": UdyamCertificate,
    "signatory_id": SignatoryId,
    "address_proof": ElectricityBill,
}


class CheckResult(BaseModel):
    code: str
    status: str                      # PASS | WARN | REVIEW | FAIL
    evidence: str = ""
    message_en: str
    message_hi: str


class KycReport(BaseModel):
    applicant: str
    verdict: str                     # PASS | REVIEW | FAIL
    checks: list[CheckResult]
    masked: dict[str, str] = Field(default_factory=dict)
    next_step_en: str = ""
    next_step_hi: str = ""
