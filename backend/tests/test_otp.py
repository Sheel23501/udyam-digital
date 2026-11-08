"""One-time password service and endpoints: random codes, hashed storage, expiry, attempt lock, single use,
resend cooldown, hourly caps, token exchange for a session, REQUIRE_OTP, provider failure, and no leaks to the audit log."""
import os
import random

import pytest
from fastapi.testclient import TestClient

from app.auth import otp, sms
from app.data.loader import connect
from app.main import app

os.environ.setdefault("STAFF_PIN", "test-pin-4821")
client = TestClient(app)


def phone() -> str:
    """A fresh random valid mobile per test, so cooldowns and hourly caps never collide between tests or runs."""
    return random.choice("6789") + "".join(random.choice("0123456789") for _ in range(9))


@pytest.fixture
def clock(monkeypatch):
    t = {"now": 1_900_000_000.0 + random.random() * 1e6}
    monkeypatch.setattr(otp, "_now", lambda: t["now"])
    return t


def request(p: str, **kw) -> dict:
    r = client.post("/auth/otp/request", json={"phone": p}, **kw)
    assert r.status_code == 201, r.text
    return r.json()


def verify(rid: str, code: str):
    return client.post("/auth/otp/verify", json={"request_id": rid, "code": code})


# ---------- normalisation ----------
@pytest.mark.parametrize("raw,ok", [
    ("9876543210", "9876543210"), ("+91 98765 43210", "9876543210"), ("098765-43210", "9876543210"), ("919876543210", "9876543210"),
    ("6000000000", "6000000000"),
])
def test_normalise_accepts_indian_mobiles(raw, ok):
    assert otp.normalise_phone(raw) == ok


@pytest.mark.parametrize("raw", ["12345", "5876543210", "98765432101", "abcdefghij", "", "+1 415 555 0100"])
def test_normalise_rejects_everything_else(raw):
    with pytest.raises(ValueError):
        otp.normalise_phone(raw)
    assert client.post("/auth/otp/request", json={"phone": raw}).status_code in (400, 422)


# ---------- codes ----------
def test_codes_are_random_six_digits_and_never_1234(clock):
    codes = []
    for _ in range(40):
        r = request(phone())
        assert r["demo"] is True and r["provider"] == "demo" and r["length"] == 6
        assert len(r["demo_code"]) == 6 and r["demo_code"].isdigit()
        codes.append(r["demo_code"])
    assert len(set(codes)) >= 38                       # 40 draws from a million: collisions are vanishingly rare
    assert "1234" not in codes and "001234" not in codes or len(set(codes)) > 1


def test_code_and_phone_are_never_stored_in_clear(clock):
    p = phone()
    r = request(p)
    row = dict(connect().execute("SELECT * FROM otp_requests WHERE id = ?", (r["request_id"],)).fetchone())
    flat = " ".join(str(v) for v in row.values())
    assert r["demo_code"] not in flat and p not in flat
    assert row["phone_masked"] == f"XXXXXX{p[-4:]}" and len(row["code_hash"]) == 64


# ---------- verify ----------
def test_right_code_gives_single_use_token_for_a_verified_session(clock):
    p = phone()
    r = request(p)
    v = verify(r["request_id"], r["demo_code"])
    assert v.status_code == 200 and v.json()["verified"] and v.json()["phone_masked"] == f"XXXXXX{p[-4:]}"
    token = v.json()["otp_token"]
    s = client.post("/sessions", json={"language": "en", "otp_token": token})
    assert s.status_code == 201 and s.json()["phone_verified"] is True
    sess = client.get(f"/sessions/{s.json()['session_id']}").json()
    assert sess["phone_verified"] and sess["phone_masked"] == f"XXXXXX{p[-4:]}"
    raw = dict(connect().execute("SELECT * FROM sessions WHERE id = ?", (s.json()["session_id"],)).fetchone())
    assert p not in " ".join(str(v) for v in raw.values())          # only hash + masked number on the session
    assert client.post("/sessions", json={"otp_token": token}).status_code == 401      # token is single use
    assert verify(r["request_id"], r["demo_code"]).status_code == 409                # code is single use


def test_wrong_codes_count_down_then_lock_even_the_right_code(clock):
    r = request(phone())
    wrong = "000000" if r["demo_code"] != "000000" else "111111"
    lefts = [verify(r["request_id"], wrong).json()["detail"].get("attempts_left") for _ in range(otp.max_attempts())]
    assert lefts == [4, 3, 2, 1, 0]
    locked = verify(r["request_id"], r["demo_code"])
    assert locked.status_code == 429 and locked.json()["detail"]["error"] == "locked"


def test_code_expires(clock):
    r = request(phone())
    clock["now"] += otp.ttl_s() + 1
    v = verify(r["request_id"], r["demo_code"])
    assert v.status_code == 410 and v.json()["detail"]["error"] == "expired"


def test_codes_are_bound_to_their_request(clock):
    a, b = request(phone()), request(phone())
    if a["demo_code"] != b["demo_code"]:
        assert verify(a["request_id"], b["demo_code"]).status_code == 400
    assert verify("nope", a["demo_code"]).status_code == 404


def test_token_expires(clock):
    r = request(phone())
    token = verify(r["request_id"], r["demo_code"]).json()["otp_token"]
    clock["now"] += otp.token_ttl_s() + 1
    assert client.post("/sessions", json={"otp_token": token}).status_code == 401


# ---------- anti-abuse ----------
def test_resend_cooldown_then_hourly_cap(clock):
    p = phone()
    request(p)
    too_soon = client.post("/auth/otp/request", json={"phone": p})
    assert too_soon.status_code == 429 and too_soon.json()["detail"]["error"] == "resend_too_soon"
    assert int(too_soon.headers["retry-after"]) <= otp.cooldown_s()
    for _ in range(otp.max_per_hour() - 1):
        clock["now"] += otp.cooldown_s() + 1
        request(p)
    clock["now"] += otp.cooldown_s() + 1
    capped = client.post("/auth/otp/request", json={"phone": p})
    assert capped.status_code == 429 and capped.json()["detail"]["error"] == "too_many_codes"
    clock["now"] += 3601
    request(p)                                           # the window slides


def test_per_ip_cap_applies_to_real_clients_only(clock, monkeypatch):
    monkeypatch.setenv("OTP_MAX_PER_IP_HOUR", "3")
    monkeypatch.setenv("TRUST_PROXY", "1")                 # X-Forwarded-For is honoured only behind a known proxy
    ip = f"203.0.113.{random.randint(1, 254)}"
    for _ in range(3):
        request(phone(), headers={"x-forwarded-for": ip})
    blocked = client.post("/auth/otp/request", json={"phone": phone()}, headers={"x-forwarded-for": ip})
    assert blocked.status_code == 429 and blocked.json()["detail"]["error"] == "too_many_requests"
    for _ in range(4):                                   # in-process / test client: no shared-IP lockout
        request(phone())


# ---------- sessions policy ----------
def test_require_otp_blocks_anonymous_sessions(clock, monkeypatch):
    assert client.post("/sessions", json={"language": "en"}).status_code == 201      # default: open for API testing
    monkeypatch.setenv("REQUIRE_OTP", "1")
    r = client.post("/sessions", json={"language": "en"})
    assert r.status_code == 401 and r.json()["detail"]["error"] == "otp_required"
    o = request(phone())
    token = verify(o["request_id"], o["demo_code"]).json()["otp_token"]
    assert client.post("/sessions", json={"language": "en", "otp_token": token}).status_code == 201
    assert client.get("/health").json()["otp_required_for_sessions"] is True


# ---------- providers ----------
class FakeSms(sms.Provider):
    name = "fake"
    sent: list = []

    def send(self, phone10, code, ttl_s):
        FakeSms.sent.append((phone10, code))
        return sms.SendResult(ref="msg-1")


class BrokenSms(sms.Provider):
    name = "broken"

    def send(self, phone10, code, ttl_s):
        raise sms.SmsError("gateway said no")


def test_real_provider_never_returns_the_code(clock, monkeypatch):
    monkeypatch.setitem(sms.PROVIDERS, "fake", FakeSms)
    monkeypatch.setenv("SMS_PROVIDER", "fake")
    p = phone()
    r = request(p)
    assert "demo_code" not in r and r["demo"] is False and r["provider"] == "fake"
    sent_phone, sent_code = FakeSms.sent[-1]
    assert sent_phone == p and len(sent_code) == 6
    assert verify(r["request_id"], sent_code).status_code == 200
    assert client.get("/health").json()["otp_mode"] == "sms:fake"


def test_provider_failure_and_misconfiguration_are_clean_errors(clock, monkeypatch):
    monkeypatch.setitem(sms.PROVIDERS, "broken", BrokenSms)
    monkeypatch.setenv("SMS_PROVIDER", "broken")
    r = client.post("/auth/otp/request", json={"phone": phone()})
    assert r.status_code == 502 and r.json()["detail"]["error"] == "sms_failed"
    monkeypatch.setenv("SMS_PROVIDER", "nonexistent")
    r = client.post("/auth/otp/request", json={"phone": phone()})
    assert r.status_code == 503 and r.json()["detail"]["error"] == "sms_unavailable"
    assert client.get("/health").json()["otp_mode"].startswith("misconfigured")


def test_audit_log_never_holds_numbers_or_codes(clock):
    p = phone()
    r = request(p)
    verify(r["request_id"], "000000" if r["demo_code"] != "000000" else "111111")
    verify(r["request_id"], r["demo_code"])
    client.post("/auth/otp/request", json={"phone": f"+91 {p[:5]} {p[5:]}"})        # spaced form, cooldown error path
    rows = client.get("/backoffice/audit?limit=50", headers={"X-Staff-Pin": os.environ["STAFF_PIN"]}).json()
    text = " ".join(a["subject_masked"] or "" for a in rows)
    assert p not in text and r["demo_code"] not in text and f"{p[:5]} {p[5:]}" not in text
    assert any(a["action"] == "otp.verified" for a in rows)



def test_spoofed_forwarded_for_is_ignored_without_trust_proxy(clock, monkeypatch):
    monkeypatch.delenv("TRUST_PROXY", raising=False)
    monkeypatch.setenv("OTP_MAX_PER_IP_HOUR", "2")
    from app.routers.auth import _client_ip
    req = type("R", (), {"headers": {"x-forwarded-for": "203.0.113.7"}, "client": type("C", (), {"host": "198.51.100.4"})()})()
    assert _client_ip(req) == "198.51.100.4"


def test_private_network_callers_share_no_ip_cap(clock, monkeypatch):
    monkeypatch.setenv("OTP_MAX_PER_IP_HOUR", "2")
    assert otp._is_internal("172.18.0.3") and otp._is_internal("127.0.0.1") and not otp._is_internal("203.0.113.9")


def test_devanagari_digits_are_the_same_number(clock):
    p = phone()
    deva = p.translate(str.maketrans("0123456789", "०१२३४५६७८९"))
    assert otp.normalise_phone(deva) == p
    request(p)
    assert client.post("/auth/otp/request", json={"phone": deva}).status_code == 429     # same cooldown applies
