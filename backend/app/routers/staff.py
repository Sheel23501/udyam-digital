"""Staff-only access for the back-office and admin endpoints: header X-Staff-Pin must equal STAFF_PIN.
With no STAFF_PIN configured the endpoints stay locked (there is no default PIN)."""
import hmac
import os

from fastapi import Header, HTTPException


def require_staff(x_staff_pin: str | None = Header(None, description="the STAFF_PIN configured on the server")) -> None:
    pin = os.getenv("STAFF_PIN", "").strip()
    if not pin:
        raise HTTPException(403, {"error": "staff_locked", "message": "Back-office API is locked: set STAFF_PIN on the server."})
    if not x_staff_pin or not hmac.compare_digest(x_staff_pin.encode(), pin.encode()):
        raise HTTPException(401, {"error": "staff_pin_required", "message": "Send the staff PIN in the X-Staff-Pin header."})
