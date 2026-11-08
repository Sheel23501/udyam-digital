"""SMS delivery for one-time passwords. One small interface, several providers, chosen by SMS_PROVIDER.

  demo  (default when nothing is configured) - nothing is sent; the API returns the code so the UI can show it as a
        clearly labelled on-screen "demo SMS". Every request still gets its own random code. Never use in production.
  (real providers are registered in PROVIDERS below; each reads its own credentials from the environment)

A provider either sends a code we generated (we verify it), or generates and verifies the code itself
(`verifies_itself = True`, e.g. Twilio Verify / 2Factor AUTOGEN), in which case `send` returns the provider's reference
and `verify(ref, phone, code)` asks the provider."""
import os
from dataclasses import dataclass


class SmsError(RuntimeError):
    """The provider could not send (bad credentials, quota, network). The message is safe to show to staff, not owners."""


@dataclass
class SendResult:
    ref: str = ""                 # provider message / verification id
    demo_code: str | None = None  # only the demo provider fills this


class Provider:
    name = "base"
    demo = False
    verifies_itself = False

    def configured(self) -> bool:
        return True

    def send(self, phone10: str, code: str | None, ttl_s: int) -> SendResult:  # pragma: no cover - interface
        raise NotImplementedError

    def verify(self, ref: str, phone10: str, code: str) -> bool:  # pragma: no cover - only for verifies_itself
        raise NotImplementedError


class DemoProvider(Provider):
    name = "demo"
    demo = True

    def send(self, phone10: str, code: str | None, ttl_s: int) -> SendResult:
        return SendResult(ref="demo", demo_code=code)


PROVIDERS: dict[str, type[Provider]] = {"demo": DemoProvider}


def message_text(code: str, ttl_s: int) -> str:
    return f"{code} is your Accel Business verification code. It is valid for {max(1, ttl_s // 60)} minutes. Do not share it with anyone."


def provider() -> Provider:
    """The configured provider. An unknown name or a provider missing its credentials raises SmsError at send time,
    rather than silently falling back to demo (which would leak codes on screen in production)."""
    name = os.getenv("SMS_PROVIDER", "demo").strip().lower() or "demo"
    cls = PROVIDERS.get(name)
    if cls is None:
        raise SmsError(f"unknown SMS_PROVIDER '{name}' (known: {', '.join(sorted(PROVIDERS))})")
    p = cls()
    if not p.configured():
        raise SmsError(f"SMS_PROVIDER '{name}' is missing its credentials")
    return p


def mode() -> str:
    """For /health: 'demo' or 'sms:<provider>' (or 'misconfigured:<reason>')."""
    try:
        p = provider()
    except SmsError as e:
        return f"misconfigured: {e}"
    return "demo" if p.demo else f"sms:{p.name}"
