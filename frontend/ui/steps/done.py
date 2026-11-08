import streamlit as st

from .. import cards, nav
from ..i18n import t


def render() -> None:
    ss = st.session_state
    cards.header(5)
    if ss.get("handoff"):
        st.markdown(f"### {t('handoff_title')}")
        st.success(t("handoff_done"))
    else:
        st.markdown(f"### {t('done_title')}")
        st.write(t("done_sub"))
    with st.container(border=True):
        st.write(t("referral"))
        st.code(f"https://accel.business/start?ref={ss.get('session_id', '')}", language=None)
    if ss.get("partner"):
        st.caption(t("partner_banner", code=ss.partner))
    st.button(t("start_again"), key="start_again", use_container_width=True, on_click=nav.reset)
