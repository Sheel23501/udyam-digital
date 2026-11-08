"""SMS provider adapters against mocked HTTP (no network, no credentials): request shape, response handling, error
mapping, token refresh, and that no secret ever reaches an error message."""
import json
import random

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth import otp, sms
from app.main import app

client = TestClient(app)


def phone() -> str:
    return random.choice("6789") + "".join(random.choice("0123456789") for _ in range(9))


@pytest.fixture
def mock_http(monkeypatch):
    calls = []
    routes = {}

    def handler(request: httpx.Request):
        calls.append(request)
        for key, fn in routes.items():
            if key in request.url.path:
                return fn(request)
        return httpx.Response(404, json={})
    monkeypatch.setattr(sms, "TRANSPORT", httpx.MockTransport(handler))
    return calls, routes


@pytest.fixture
def mc_env(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "messagecentral")
    monkeypatch.setenv("MC_CUSTOMER_ID", "C-TEST1234")
    monkeypatch.setenv("MC_EMAIL", "owner@example.com")
    monkeypatch.setenv("MC_PASSWORD", "s3cret-pass")
    sms.MessageCentral._token = {}


def mc_routes(routes, verify_code=200, verify_status="VERIFICATION_COMPLETED", send_code=200):
    routes["/auth/v1/authentication/token"] = lambda r: httpx.Response(200, json={"status": 200, "token": "TOK"})
    routes["/verification/v3/send"] = lambda r: httpx.Response(200, json={
        "responseCode": send_code, "message": "SUCCESS" if send_code == 200 else "ERR",
        "data": {"verificationId": "VID-1", "timeout": "60"} if send_code == 200 else {}})
    routes["/verification/v3/validateOtp"] = lambda r: httpx.Response(200, json={
        "responseCode": verify_code, "data": {"verificationStatus": verify_status if verify_code == 200 else None}})


def test_messagecentral_full_flow(mock_http, mc_env):
    calls, routes = mock_http
    mc_routes(routes)
    p = phone()
    r = client.post("/auth/otp/request", json={"phone": p})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["provider"] == "messagecentral" and body["demo"] is False and "demo_code" not in body
    assert body["expires_in"] == 60 and body["resend_in"] >= 30            # provider validity is 60 s
    send = next(c for c in calls if "/send" in c.url.path)
    assert send.method == "POST" and send.headers["authToken"] == "TOK"
    q = dict(send.url.params)
    assert q["mobileNumber"] == p and q["countryCode"] == "91" and q["otpLength"] == "6" and q["customerId"] == "C-TEST1234"
    v = client.post("/auth/otp/verify", json={"request_id": body["request_id"], "code": "482913"})
    assert v.status_code == 200 and v.json()["verified"]
    val = next(c for c in calls if "validateOtp" in c.url.path)
    assert dict(val.url.params) == {"verificationId": "VID-1", "code": "482913", "flowType": "SMS"}


@pytest.mark.parametrize("vcode,status,expected_http,expected_err", [
    (702, None, 400, "wrong_code"), (705, None, 410, "expired"), (703, None, 409, "already_used"), (500, None, 503, "sms_unavailable"),
])
def test_messagecentral_verify_error_mapping(mock_http, mc_env, vcode, status, expected_http, expected_err):
    calls, routes = mock_http
    mc_routes(routes, verify_code=vcode)
    rid = client.post("/auth/otp/request", json={"phone": phone()}).json()["request_id"]
    v = client.post("/auth/otp/verify", json={"request_id": rid, "code": "123456"})
    assert v.status_code == expected_http and v.json()["detail"]["error"] == expected_err


def test_messagecentral_resend_too_soon_and_send_failure(mock_http, mc_env):
    calls, routes = mock_http
    mc_routes(routes, send_code=506)
    r = client.post("/auth/otp/request", json={"phone": phone()})
    assert r.status_code == 429 and r.json()["detail"]["error"] == "resend_too_soon"
    mc_routes(routes, send_code=400)
    r = client.post("/auth/otp/request", json={"phone": phone()})
    assert r.status_code == 502 and r.json()["detail"]["error"] == "sms_failed"


def test_messagecentral_refreshes_an_expired_token(mock_http, mc_env):
    calls, routes = mock_http
    mc_routes(routes)
    state = {"n": 0}

    def send(r):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(401, content=b"")
        return httpx.Response(200, json={"responseCode": 200, "data": {"verificationId": "VID-2", "timeout": "60"}})
    routes["/verification/v3/send"] = send
    assert client.post("/auth/otp/request", json={"phone": phone()}).status_code == 201
    assert sum("/authentication/token" in c.url.path for c in calls) == 2


def test_messagecentral_bad_credentials_never_leak(mock_http, mc_env):
    calls, routes = mock_http
    routes["/auth/v1/authentication/token"] = lambda r: httpx.Response(200, json={"status": 400, "error": "customerId is invalid"})
    with pytest.raises(sms.SmsError) as e:
        sms.MessageCentral().send(phone(), None, 300)
    assert "customerId is invalid" in str(e.value) and "s3cret" not in str(e.value) and "c2VjcmV0" not in str(e.value)
    r = client.post("/auth/otp/request", json={"phone": phone()})
    assert r.status_code == 502 and "s3cret" not in r.text


def test_messagecentral_missing_credentials_is_misconfigured(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "messagecentral")
    for k in ("MC_CUSTOMER_ID", "MC_EMAIL", "MC_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    assert client.get("/health").json()["otp_mode"].startswith("misconfigured")
    assert client.post("/auth/otp/request", json={"phone": phone()}).status_code == 503


@pytest.fixture
def tf_env(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "2factor")
    monkeypatch.setenv("TWOFACTOR_API_KEY", "KEY-abc-123")
    monkeypatch.delenv("TWOFACTOR_TEMPLATE", raising=False)


@pytest.mark.parametrize("details,expected_http,expected_err", [
    ("OTP Matched", 200, None), ("OTP Mismatch", 400, "wrong_code"), ("OTP Expired", 410, "expired"),
])
def test_twofactor_flow(mock_http, tf_env, details, expected_http, expected_err):
    calls, routes = mock_http
    routes["/AUTOGEN"] = lambda r: httpx.Response(200, json={"Status": "Success", "Details": "SESSION-9"})
    routes["/SMS/VERIFY/"] = lambda r: httpx.Response(200, json={"Status": "Success" if details == "OTP Matched" else "Error", "Details": details})
    p = phone()
    r = client.post("/auth/otp/request", json={"phone": p})
    assert r.status_code == 201 and r.json()["provider"] == "2factor" and "demo_code" not in r.json()
    assert calls[-1].url.path == f"/API/V1/KEY-abc-123/SMS/{p}/AUTOGEN"
    v = client.post("/auth/otp/verify", json={"request_id": r.json()["request_id"], "code": "123456"})
    assert v.status_code == expected_http
    if expected_err:
        assert v.json()["detail"]["error"] == expected_err
    assert calls[-1].url.path == "/API/V1/KEY-abc-123/SMS/VERIFY/SESSION-9/123456"


def test_twofactor_send_error_hides_the_key(mock_http, tf_env):
    calls, routes = mock_http
    routes["/AUTOGEN"] = lambda r: httpx.Response(200, json={"Status": "Error", "Details": "Invalid API Key"})
    r = client.post("/auth/otp/request", json={"phone": phone()})
    assert r.status_code == 502 and "KEY-abc-123" not in r.text
    audit = json.dumps(client.get("/backoffice/audit?limit=20").json())
    assert "KEY-abc-123" not in audit


def test_malformed_code_counts_without_calling_the_provider(mock_http, tf_env):
    calls, routes = mock_http
    routes["/AUTOGEN"] = lambda r: httpx.Response(200, json={"Status": "Success", "Details": "S"})
    rid = client.post("/auth/otp/request", json={"phone": phone()}).json()["request_id"]
    n = len(calls)
    v = client.post("/auth/otp/verify", json={"request_id": rid, "code": "12"})
    assert v.status_code == 400 and v.json()["detail"]["attempts_left"] == otp.max_attempts() - 1 and len(calls) == n
