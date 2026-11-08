import re

import streamlit as st

import api_client as api

from .. import cards, nav
from ..i18n import t

DEMO_OTP = "1234"


def render() -> None:
    cards.header(0)
    st.markdown(f"### {t('otp_title')}")
    st.caption(t("otp_sub"))
    ss = st.session_state
    phone = st.text_input(t("phone"), key="phone", max_chars=13, placeholder="98765 43210")
    digits = re.sub(r"\D", "", phone or "")
    if not ss.get("otp_sent"):
        if st.button(t("send_otp"), key="send_otp", type="primary", use_container_width=True):
            if len(digits) == 10 and digits[0] in "6789":
                ss.otp_sent = True
                ss.phone_digits = digits
                st.rerun()
            else:
                st.error(t("bad_phone"))
        return
    st.success(t("otp_sent", phone=f"XXXXXX{ss.phone_digits[-4:]}"))
    code = st.text_input(t("otp"), key="otp_code", max_chars=6, placeholder="1234")
    if st.button(t("verify"), key="verify_otp", type="primary", use_container_width=True):
        if (code or "").strip() != DEMO_OTP:
            st.error(t("bad_otp"))
            return
        try:
            r = api.post("/sessions", json={"language": ss.lang, "partner_code": ss.get("partner"), "referrer": ss.get("ref")})
        except api.ApiError as e:
            cards.api_error(e)
            return
        ss.session_id = r["session_id"]
        ss.transcript = [{"role": "assistant", "text": t("opening")}]
        nav.go("chat")
