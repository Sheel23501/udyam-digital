import streamlit as st

import api_client as api

from .. import cards, nav
from ..i18n import lang, t


def render() -> None:
    ss = st.session_state
    cards.header(5)
    st.markdown(f"### {t('tracker_title')}")
    st.caption(t("tracker_sub"))
    try:
        order = api.get(f"/orders/{ss.order_id}")
    except api.ApiError as e:
        cards.api_error(e)
        return
    with st.container(border=True):
        st.caption(order["order_id"])
        st.progress(order["progress"], text=order["labels"][order["status"]][lang()])
        cards.timeline(order)
        b = order["bundle"]
        st.caption(" · ".join(f"{i['name']}" + (f" × {i['qty']}" if i["qty"] > 1 else "") for i in b["items"]))
        st.caption(f"₹{b['monthly_min']:,} {t('per_month')} · {t('setup')} ₹{b['setup']:,}")
    st.toggle(t("notify"), value=True, key="notify", help=t("notify_demo"))
    st.caption(t("notify_demo"))
    if order["stage_index"] < len(order["stages"]) - 1:
        if st.button(t("advance_demo"), key="advance", use_container_width=True):
            try:
                o = api.post(f"/orders/{ss.order_id}/advance")
            except api.ApiError as e:
                cards.api_error(e)
                return
            st.toast(t("advanced_toast", label=o["labels"][o["status"]][lang()], date=o["eta"].get(o["status"], "")), icon="📲")
            st.rerun()
    with st.expander(t("withdraw_title")):
        st.write(t("withdraw_text"))
        if ss.get("consent_withdrawn"):
            st.success(t("withdrawn"))
        elif st.button(t("withdraw_btn"), key="withdraw"):
            try:
                api.delete(f"/consent/{ss.session_id}/{ss.consent_id}")
            except api.ApiError as e:
                cards.api_error(e)
                return
            ss.consent_withdrawn = True
            st.rerun()
    st.button(t("finish"), key="finish", type="primary", use_container_width=True, on_click=nav.set_step, args=("done",))
