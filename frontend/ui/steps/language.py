import streamlit as st

from .. import cards, nav
from ..i18n import t


def _pick(code: str) -> None:
    st.session_state.lang = code
    nav.set_step("otp")


def render() -> None:
    cards.header()
    st.markdown(f"### {t('welcome')}")
    st.caption(t("welcome_sub"))
    if st.session_state.get("partner"):
        st.info(t("partner_banner", code=st.session_state.partner), icon="🤝")
    st.markdown(f"**{t('choose_lang')}**")
    c1, c2 = st.columns(2)
    with c1:
        st.button("हिंदी", key="lang_hi", use_container_width=True, type="primary", on_click=_pick, args=("hi",))
    with c2:
        st.button("English", key="lang_en", use_container_width=True, on_click=_pick, args=("en",))
    st.caption("हिंदी · English · Hinglish bhi chalega")
