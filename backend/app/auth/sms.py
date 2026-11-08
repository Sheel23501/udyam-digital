"""SMS delivery for one-time passwords. One small interface, several providers, chosen by SMS_PROVIDER.

  demo            (default) nothing is sent; the API returns the code so the UI can show it as a clearly labelled
                  on-screen "demo SMS". Every request still gets its own random code. Never use in production.
  messagecentral  Message Central VerifyNow: no card, no DLT registration of our own (their approved OTP template,
                  sender UTOMOB), free test credits. They generate and check the code.
                  env: MC_CUSTOMER_ID, MC_EMAIL, MC_PASSWORD
  2factor         2Factor.in AUTOGEN on the default OTP template; free test credits. They generate and check the code.
                  env: TWOFACTOR_API_KEY, optional TWOFACTOR_TEMPLATE

A provider either sends a code we generated (we verify it), or generates and verifies the code itself
(`verifies_itself = True`), in which case `send` returns the provider's reference and `verify(ref, code)` asks it.
Secrets live in URLs/query strings for both real providers, so no URL or response body with a key is ever logged or
put into an error message."""
import base64
import os
import threading
import time
from dataclasses import dataclass

import httpx

TRANSPORT: httpx.BaseTransport | None = None      # tests inject an httpx.MockTransport here
TIMEOUT_S = 15.0


class SmsError(RuntimeError):
    """The provider could not send or check (bad credentials, quota, network). Safe to show to staff, not owners."""


class SmsTooSoon(SmsError):
    def __init__(self, retry_after: int, message: str = "a code was sent to this number moments ago"):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class SendResult:
    ref: str = ""                 # provider verification / session id
    demo_code: str | None = None  # only the demo provider fills this
    ttl_s: int | None = None      # provider-side validity, when shorter than ours


OK, WRONG, EXPIRED, USED = "ok", "wrong", "expired", "used"


def _http() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S, transport=TRANSPORT)


class Provider:
    name = "base"
    demo = False
    verifies_itself = False

    def configured(self) -> bool:
        return True

    def send(self, phone10: str, code: str | None, ttl_s: int) -> SendResult:  # pragma: no cover - interface
        raise NotImplementedError

    def verify(self, ref: str, code: str) -> str:  # pragma: no cover - only for verifies_itself
        raise NotImplementedError


class DemoProvider(Provider):
    name = "demo"
    demo = True

    def send(self, phone10: str, code: str | None, ttl_s: int) -> SendResult:
        return SendResult(ref="demo", demo_code=code)


class MessageCentral(Provider):
    """https://www.messagecentral.com/en-in/product/verify-now/api-india"""
    name = "messagecentral"
    verifies_itself = True
    BASE = "https://cpaas.messagecentral.com"
    _token: dict = {}
    _lock = threading.Lock()

    def __init__(self):
        self.customer_id = os.getenv("MC_CUSTOMER_ID", "").strip()
        self.email = os.getenv("MC_EMAIL", "").strip()
        self.password = os.getenv("MC_PASSWORD", "")

    def configured(self) -> bool:
        return bool(self.customer_id and self.email and self.password)

    def _get_token(self, force: bool = False) -> str:
        with self._lock:
            cached = MessageCentral._token
            if not force and cached.get("cid") == self.customer_id and cached.get("exp", 0) > time.time():
                return cached["token"]
            key = base64.b64encode(self.password.encode()).decode()
            try:
                with _http() as c:
                    r = c.get(f"{self.BASE}/auth/v1/authentication/token",
                              params={"customerId": self.customer_id, "key": key, "scope": "NEW", "country": "91", "email": self.email},
                              headers={"accept": "*/*"})
                js = r.json()
            except (httpx.HTTPError, ValueError) as e:
                raise SmsError(f"messagecentral: token request failed ({type(e).__name__})") from None
            token = js.get("token")
            if r.status_code != 200 or not token or js.get("status") not in (None, 200):
                raise SmsError(f"messagecentral: authentication failed ({js.get('error') or js.get('status') or r.status_code})")
            MessageCentral._token = {"cid": self.customer_id, "token": token, "exp": time.time() + 15 * 60}
            return token

    def _call(self, method: str, path: str, params: dict) -> tuple[int, dict]:
        for attempt in (0, 1):
            token = self._get_token(force=attempt == 1)
            try:
                with _http() as c:
                    r = c.request(method, f"{self.BASE}{path}", params=params, headers={"authToken": token})
            except httpx.HTTPError as e:
                raise SmsError(f"messagecentral: network error ({type(e).__name__})") from None
            if r.status_code == 401 and attempt == 0:
                continue                                       # token expired: fetch a new one once
            try:
                js = r.json() if r.content else {}
            except ValueError:
                js = {}
            code = js.get("responseCode") or (js.get("data") or {}).get("responseCode") or r.status_code
            try:
                code = int(code)
            except (TypeError, ValueError):
                code = r.status_code
            return code, js
        raise SmsError("messagecentral: authentication rejected")

    def send(self, phone10: str, code: str | None, ttl_s: int) -> SendResult:
        rc, js = self._call("POST", "/verification/v3/send", {
            "countryCode": "91", "customerId": self.customer_id, "flowType": "SMS", "mobileNumber": phone10, "otpLength": "6"})
        data = js.get("data") or {}
        if rc == 200 and data.get("verificationId"):
            try:
                provider_ttl = int(data.get("timeout") or 0) or None
            except (TypeError, ValueError):
                provider_ttl = None
            return SendResult(ref=str(data["verificationId"]), ttl_s=provider_ttl)
        if rc == 506:
            raise SmsTooSoon(60)
        if rc == 800:
            raise SmsError("messagecentral: maximum limit reached for this number")
        raise SmsError(f"messagecentral: send failed (code {rc}, {js.get('message') or data.get('errorMessage') or 'no message'})")

    def verify(self, ref: str, code: str) -> str:
        rc, js = self._call("GET", "/verification/v3/validateOtp", {"verificationId": ref, "code": code, "flowType": "SMS"})
        data = js.get("data") or {}
        if rc == 200 and data.get("verificationStatus") == "VERIFICATION_COMPLETED":
            return OK
        if rc == 702:
            return WRONG
        if rc in (705, 505):
            return EXPIRED
        if rc == 703:
            return USED
        raise SmsError(f"messagecentral: verify failed (code {rc})")


class TwoFactor(Provider):
    """https://2factor.in  (API key is part of the URL path: never log URLs)"""
    name = "2factor"
    verifies_itself = True
    BASE = "https://2factor.in/API/V1"

    def __init__(self):
        self.key = os.getenv("TWOFACTOR_API_KEY", "").strip()
        self.template = os.getenv("TWOFACTOR_TEMPLATE", "").strip()

    def configured(self) -> bool:
        return bool(self.key)

    def _get(self, path: str) -> dict:
        try:
            with _http() as c:
                r = c.get(f"{self.BASE}/{self.key}/{path}")
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise SmsError(f"2factor: request failed ({type(e).__name__})") from None

    def send(self, phone10: str, code: str | None, ttl_s: int) -> SendResult:
        path = f"SMS/{phone10}/AUTOGEN" + (f"/{self.template}" if self.template else "")
        js = self._get(path)
        if js.get("Status") == "Success" and js.get("Details"):
            return SendResult(ref=str(js["Details"]))
        raise SmsError(f"2factor: send failed ({js.get('Details') or 'no details'})")

    def verify(self, ref: str, code: str) -> str:
        js = self._get(f"SMS/VERIFY/{ref}/{code}")
        details = str(js.get("Details") or "").lower()
        if js.get("Status") == "Success" and "matched" in details:
            return OK
        if "mismatch" in details:
            return WRONG
        if "expired" in details:
            return EXPIRED
        raise SmsError(f"2factor: verify failed ({js.get('Details') or 'no details'})")


PROVIDERS: dict[str, type[Provider]] = {"demo": DemoProvider, "messagecentral": MessageCentral, "2factor": TwoFactor}


def message_text(code: str, ttl_s: int) -> str:
    return f"{code} is your Accel Business verification code. It is valid for {max(1, ttl_s // 60)} minutes. Do not share it with anyone."


def provider() -> Provider:
    """The configured provider. An unknown name or a provider missing its credentials raises SmsError, rather than
    silently falling back to demo (which would show codes on screen in production)."""
    name = os.getenv("SMS_PROVIDER", "demo").strip().lower() or "demo"
    cls = PROVIDERS.get(name)
    if cls is None:
        raise SmsError(f"unknown SMS_PROVIDER '{name}' (known: {', '.join(sorted(PROVIDERS))})")
    p = cls()
    if not p.configured():
        raise SmsError(f"SMS_PROVIDER '{name}' is missing its credentials")
    return p


def mode() -> str:
    """For /health: 'demo' or 'sms:<provider>' (or 'misconfigured: <reason>')."""
    try:
        p = provider()
    except SmsError as e:
        return f"misconfigured: {e}"
    return "demo" if p.demo else f"sms:{p.name}"
