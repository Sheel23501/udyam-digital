"""Mobile number + one-time password. The backend generates a fresh random code per request and sends it by SMS;
in demo mode (no SMS gateway configured) the API returns the code and this screen shows it as a labelled demo SMS."""
import html
import time

import streamlit as st

import api_client as api

from .. import cards, nav
from ..i18n import t


def _reset() -> None:
    for k in ("otp", "otp_code", "otp_error"):
        st.session_state.pop(k, None)


def _send(phone: str) -> None:
    ss = st.session_state
    try:
        r = api.post("/auth/otp/request", json={"phone": phone})
    except api.ApiError as e:
        d = e.detail if isinstance(e.detail, dict) else {}
        code = d.get("error")
        if code == "invalid_phone":
            st.error(t("bad_phone"))
        elif code in ("resend_too_soon", "too_many_codes", "too_many_requests"):
            st.error(t("otp_wait", s=d.get("retry_after", 30)))
        else:
            st.error(t("otp_send_failed"))
        return
    ss.otp = {**r, "sent_at": time.time()}
    ss.pop("otp_code", None)
    ss.pop("otp_error", None)
    st.rerun()


def _verify(code: str) -> None:
    ss = st.session_state
    o = ss.otp
    try:
        v = api.post("/auth/otp/verify", json={"request_id": o["request_id"], "code": code})
    except api.ApiError as e:
        d = e.detail if isinstance(e.detail, dict) else {}
        err = d.get("error")
        if err == "wrong_code":
            ss.otp_error = t("bad_otp_left", n=d.get("attempts_left", 0))
        elif err == "expired":
            ss.otp_error = t("otp_expired")
        elif err in ("locked", "already_used"):
            ss.otp_error = t("otp_locked")
        else:
            ss.otp_error = t("otp_send_failed")
        st.rerun()
        return
    try:
        s = api.post("/sessions", json={"language": ss.lang, "partner_code": ss.get("partner"), "referrer": ss.get("ref"),
                                         "otp_token": v["otp_token"]})
    except api.ApiError as e:
        cards.api_error(e)
        return
    ss.session_id = s["session_id"]
    ss.phone_masked = s.get("phone_masked")
    ss.transcript = [{"role": "assistant", "text": t("opening")}]
    _reset()
    nav.go("chat")


def render() -> None:
    ss = st.session_state
    cards.header(0)
    st.markdown(f"### {t('otp_title')}")
    st.caption(t("otp_sub"))
    o = ss.get("otp")

    if not o:
        phone = st.text_input(t("phone"), key="phone", max_chars=16, placeholder="98765 43210")
        if st.button(t("send_otp"), key="send_otp", type="primary", use_container_width=True):
            _send(phone)
        return

    st.success(t("otp_sent", phone=o["phone_masked"]))
    if o.get("demo"):
        st.markdown(
            f"<div class='sms'><div class='sms-from'>ACCELB · {t('demo_sms_label')}</div>"
            f"<div><b>{html.escape(str(o['demo_code']))}</b> {t('demo_sms_text', m=max(1, o['expires_in'] // 60))}</div></div>",
            unsafe_allow_html=True)
        st.caption(t("demo_sms_note"))

    code = st.text_input(t("otp"), key="otp_code", max_chars=o.get("length", 6), placeholder="• • • • • •")
    if ss.get("otp_error"):
        st.error(ss.otp_error)
    if st.button(t("verify"), key="verify_otp", type="primary", use_container_width=True):
        _verify((code or "").strip())

    left = int(o["resend_in"] - (time.time() - o["sent_at"]))
    c1, c2 = st.columns(2)
    with c1:
        if st.button(t("resend") if left <= 0 else t("resend_in", s=left), key="resend_otp", use_container_width=True, disabled=left > 0):
            ss.pop("otp", None)
            _send(ss.get("phone", ""))
    with c2:
        st.button(t("change_number"), key="change_number", use_container_width=True, on_click=_reset)
