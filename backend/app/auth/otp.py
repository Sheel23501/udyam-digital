"""One-time passwords for mobile verification.

- A fresh random 6-digit code per request (secrets.randbelow), never a fixed code.
- Stored only as HMAC-SHA256(server secret, request id + code); the phone number only as an HMAC and a masked form.
- Expires after OTP_TTL_S (5 min), single use, locked after OTP_MAX_ATTEMPTS (5) wrong tries.
- Anti-abuse: resend cooldown per number (30 s), at most OTP_MAX_PER_HOUR sends per number (5) and per client IP (20).
  In in-process mode (Streamlit Cloud) every request comes from the same internal client, so the IP limit is skipped
  there; the per-number limits still hold.
- A verified code yields a short-lived single-use token that POST /sessions exchanges for a phone-verified session.

The server secret comes from OTP_SECRET, else from data/.otp_secret (generated once, gitignored)."""
import hashlib
import hmac
import math
import os
import re
import secrets
import time
import uuid
from pathlib import Path

from ..config import DATA_DIR
from ..data.loader import connect
from . import sms

OTP_LENGTH = 6
INTERNAL_CLIENTS = {"testclient", "", None}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def ttl_s() -> int:
    return _int_env("OTP_TTL_S", 300)


def max_attempts() -> int:
    return _int_env("OTP_MAX_ATTEMPTS", 5)


def cooldown_s() -> int:
    return _int_env("OTP_RESEND_COOLDOWN_S", 30)


def max_per_hour() -> int:
    return _int_env("OTP_MAX_PER_HOUR", 5)


def max_per_ip_hour() -> int:
    return _int_env("OTP_MAX_PER_IP_HOUR", 20)


def token_ttl_s() -> int:
    return _int_env("OTP_TOKEN_TTL_S", 900)


_now = time.time          # monkeypatched by tests


class OtpError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra

    def detail(self) -> dict:
        return {"error": self.code, "message": self.message, **self.extra}


SCHEMA = """
CREATE TABLE IF NOT EXISTS otp_requests (
  id TEXT PRIMARY KEY, phone_hash TEXT NOT NULL, phone_masked TEXT NOT NULL, code_hash TEXT,
  created REAL NOT NULL, expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, verified_at REAL,
  token_hash TEXT, token_expires REAL, consumed_at REAL, ip_hash TEXT, provider TEXT, provider_ref TEXT
);
CREATE INDEX IF NOT EXISTS ix_otp_phone ON otp_requests(phone_hash, created);
CREATE INDEX IF NOT EXISTS ix_otp_ip ON otp_requests(ip_hash, created);
CREATE INDEX IF NOT EXISTS ix_otp_token ON otp_requests(token_hash);
"""
_schema_ready = False


def _db():
    global _schema_ready
    con = connect()
    if not _schema_ready:
        con.executescript(SCHEMA)
        con.commit()
        _schema_ready = True
    return con


def _secret() -> bytes:
    env = os.getenv("OTP_SECRET", "").strip()
    if env:
        return env.encode()
    path = Path(DATA_DIR) / ".otp_secret"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return path.read_text().strip().encode()


def _mac(*parts: str) -> str:
    return hmac.new(_secret(), "|".join(parts).encode(), hashlib.sha256).hexdigest()


PHONE_RE = re.compile(r"^[6-9]\d{9}$")


def normalise_phone(raw: str) -> str:
    """'+91 98765-43210', '098765 43210', '9876543210' -> '9876543210'. ValueError for anything that is not an Indian mobile."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not PHONE_RE.match(digits):
        raise ValueError("not a 10-digit Indian mobile number starting with 6, 7, 8 or 9")
    return digits


def mask_phone(phone10: str) -> str:
    return f"XXXXXX{phone10[-4:]}"


def phone_hash(phone10: str) -> str:
    return _mac("phone", phone10)


def _code_hash(request_id: str, code: str) -> str:
    return _mac("code", request_id, code)


def _rate_limits(ph: str, iph: str | None, now: float) -> None:
    con = _db()
    last = con.execute("SELECT created FROM otp_requests WHERE phone_hash = ? ORDER BY created DESC LIMIT 1", (ph,)).fetchone()
    if last and now - last["created"] < cooldown_s():
        wait = max(1, math.ceil(cooldown_s() - (now - last["created"])))
        raise OtpError(429, "resend_too_soon", f"Please wait {wait} seconds before asking for a new code.", retry_after=wait)
    sent = con.execute("SELECT COUNT(*) FROM otp_requests WHERE phone_hash = ? AND created > ?", (ph, now - 3600)).fetchone()[0]
    if sent >= max_per_hour():
        first = con.execute("SELECT MIN(created) FROM otp_requests WHERE phone_hash = ? AND created > ?", (ph, now - 3600)).fetchone()[0]
        wait = max(1, math.ceil(3600 - (now - first)))
        raise OtpError(429, "too_many_codes", "Too many codes for this number. Please try again later.", retry_after=wait)
    if iph:
        by_ip = con.execute("SELECT COUNT(*) FROM otp_requests WHERE ip_hash = ? AND created > ?", (iph, now - 3600)).fetchone()[0]
        if by_ip >= max_per_ip_hour():
            raise OtpError(429, "too_many_requests", "Too many verification requests from this device. Please try again later.", retry_after=600)


def request_code(raw_phone: str, client_ip: str | None = None) -> dict:
    """Create and send a new code. Returns what the UI needs; `demo_code` is present only with the demo provider."""
    try:
        phone10 = normalise_phone(raw_phone)
    except ValueError as e:
        raise OtpError(400, "invalid_phone", str(e)) from None
    now = _now()
    ph = phone_hash(phone10)
    iph = None if client_ip in INTERNAL_CLIENTS else _mac("ip", client_ip)
    _rate_limits(ph, iph, now)
    try:
        prov = sms.provider()
    except sms.SmsError as e:
        raise OtpError(503, "sms_unavailable", "We could not send a code right now. Please try again shortly.", reason=str(e)) from None
    request_id = uuid.uuid4().hex
    code = None if prov.verifies_itself else f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"
    try:
        result = prov.send(phone10, code, ttl_s())
    except sms.SmsTooSoon as e:
        raise OtpError(429, "resend_too_soon", f"Please wait {e.retry_after} seconds before asking for a new code.", retry_after=e.retry_after) from None
    except sms.SmsError as e:
        raise OtpError(502, "sms_failed", "We could not send the code. Please check the number and try again.", reason=str(e)) from None
    valid_for = min(ttl_s(), result.ttl_s) if result.ttl_s else ttl_s()     # provider codes may expire sooner (e.g. 60 s)
    con = _db()
    con.execute(
        "INSERT INTO otp_requests(id, phone_hash, phone_masked, code_hash, created, expires, ip_hash, provider, provider_ref) VALUES (?,?,?,?,?,?,?,?,?)",
        (request_id, ph, mask_phone(phone10), _code_hash(request_id, code) if code else None, now, now + valid_for, iph, prov.name, result.ref))
    con.commit()
    out = {"request_id": request_id, "phone_masked": mask_phone(phone10), "expires_in": valid_for, "resend_in": max(cooldown_s(), min(valid_for, 60) if result.ttl_s else 0),
           "length": OTP_LENGTH, "provider": prov.name, "demo": prov.demo}
    if prov.demo:
        out["demo_code"] = result.demo_code
        out["demo_notice"] = "Demo mode: no SMS gateway is configured, so the code is shown here instead of being sent."
    return out


def verify_code(request_id: str, code: str) -> dict:
    """Check a code. Every attempt counts, right or wrong; a right code yields a single-use session token."""
    con = _db()
    row = con.execute("SELECT * FROM otp_requests WHERE id = ?", (request_id or "",)).fetchone()
    if not row:
        raise OtpError(404, "unknown_request", "This code request was not found. Please ask for a new code.")
    now = _now()
    if row["verified_at"]:
        raise OtpError(409, "already_used", "This code was already used. Please ask for a new code.")
    if now > row["expires"]:
        raise OtpError(410, "expired", "This code has expired. Please ask for a new code.")
    if row["attempts"] >= max_attempts():
        raise OtpError(429, "locked", "Too many wrong tries. Please ask for a new code.")
    attempts = row["attempts"] + 1
    con.execute("UPDATE otp_requests SET attempts = ? WHERE id = ?", (attempts, request_id))
    con.commit()
    entered = re.sub(r"\D", "", code or "")
    if row["code_hash"]:
        ok = len(entered) == OTP_LENGTH and hmac.compare_digest(row["code_hash"], _code_hash(request_id, entered))
    elif len(entered) != OTP_LENGTH:
        ok = False                                            # malformed: count the try without asking the provider
    else:
        try:
            status = sms.PROVIDERS[row["provider"]]().verify(row["provider_ref"], entered)
        except (KeyError, sms.SmsError):
            raise OtpError(503, "sms_unavailable", "We could not check the code right now. Please try again shortly.") from None
        if status == sms.EXPIRED:
            raise OtpError(410, "expired", "This code has expired. Please ask for a new code.")
        if status == sms.USED:
            raise OtpError(409, "already_used", "This code was already used. Please ask for a new code.")
        ok = status == sms.OK
    if not ok:
        left = max(0, max_attempts() - attempts)
        if left == 0:
            raise OtpError(429, "locked", "Too many wrong tries. Please ask for a new code.", attempts_left=0)
        raise OtpError(400, "wrong_code", f"That code is not right. {left} {'try' if left == 1 else 'tries'} left.", attempts_left=left)
    token = secrets.token_urlsafe(24)
    con.execute("UPDATE otp_requests SET verified_at = ?, token_hash = ?, token_expires = ? WHERE id = ?",
                (now, _mac("token", token), now + token_ttl_s(), request_id))
    con.commit()
    return {"verified": True, "otp_token": token, "phone_masked": row["phone_masked"], "token_expires_in": token_ttl_s()}


def consume_token(token: str) -> dict | None:
    """Exchange a verified-OTP token (once) for the phone identity. None if unknown, expired or already used."""
    if not token:
        return None
    con = _db()
    row = con.execute("SELECT * FROM otp_requests WHERE token_hash = ?", (_mac("token", token),)).fetchone()
    now = _now()
    if not row or row["consumed_at"] or not row["token_expires"] or now > row["token_expires"]:
        return None
    cur = con.execute("UPDATE otp_requests SET consumed_at = ? WHERE id = ? AND consumed_at IS NULL", (now, row["id"]))
    con.commit()
    if cur.rowcount != 1:                                     # lost a race with a parallel exchange
        return None
    return {"phone_hash": row["phone_hash"], "phone_masked": row["phone_masked"]}


def require_otp() -> bool:
    return os.getenv("REQUIRE_OTP", "0").strip().lower() in ("1", "true", "yes")
