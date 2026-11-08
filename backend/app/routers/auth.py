"""Mobile verification by one-time password."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..auth import otp
from ..privacy import audit

router = APIRouter(tags=["auth"])


class OtpRequestIn(BaseModel):
    phone: str = Field(..., description="Indian mobile number; +91, a leading 0, spaces and dashes are accepted")


class OtpVerifyIn(BaseModel):
    request_id: str
    code: str = Field(..., min_length=1, max_length=12)


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/auth/otp/request", status_code=201)
def request_otp(body: OtpRequestIn, request: Request) -> dict:
    """Send a fresh random 6-digit code to the number. With SMS_PROVIDER unset (demo mode) the code is returned in the
    response as `demo_code` so the UI can show it; with a real provider it is only sent by SMS."""
    try:
        out = otp.request_code(body.phone, _client_ip(request))
    except otp.OtpError as e:
        try:
            subject = otp.mask_phone(otp.normalise_phone(body.phone))
        except ValueError:
            subject = "invalid number"                       # never log what was typed: it may still be a real number
        audit.log("owner", f"otp.request.{e.code}", subject)
        raise HTTPException(e.status, e.detail(), headers={"Retry-After": str(e.extra["retry_after"])} if "retry_after" in e.extra else None) from None
    audit.log("owner", "otp.request", f"{out['phone_masked']} via {out['provider']}")
    return out


@router.post("/auth/otp/verify")
def verify_otp(body: OtpVerifyIn) -> dict:
    """Check the code. Returns a single-use `otp_token` to pass to POST /sessions."""
    try:
        out = otp.verify_code(body.request_id, body.code)
    except otp.OtpError as e:
        audit.log("owner", f"otp.verify.{e.code}", body.request_id[:8])
        raise HTTPException(e.status, e.detail()) from None
    audit.log("owner", "otp.verified", out["phone_masked"])
    return out
