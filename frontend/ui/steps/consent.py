import streamlit as st

import api_client as api

from .. import cards, nav
from ..i18n import lang, t


@st.cache_data(show_spinner=False, ttl=3600)
def notice(language: str) -> dict:
    return api.get("/consent/notice", lang=language)


def render() -> None:
    ss = st.session_state
    cards.header(3)
    st.markdown(f"### {t('consent_title')}")
    st.caption(t("consent_sub"))
    try:
        n = notice(lang())
    except api.ApiError as e:
        cards.api_error(e)
        return
    ticked: list[str] = []
    for p in n["purposes"]:
        tag = t("required") if p["required"] else t("optional")
        if st.checkbox(f"{p['label']}  \n:gray[({tag})]", key=f"purpose_{p['id']}", value=False):
            ticked.append(p["id"])
    with st.expander(t("notice_full")):
        st.write(n["text"])
        st.caption(f"Notice version {n['version']} · DPDP Act 2023")
    required = [p["id"] for p in n["purposes"] if p["required"]]
    ok = all(r in ticked for r in required)
    if not ok:
        st.caption(t("tick_all"))
    if st.button(t("agree"), key="agree", type="primary", use_container_width=True, disabled=not ok):
        try:
            r = api.post("/consent", json={"session_id": ss.session_id, "purposes": ticked, "language": lang(), "notice_version": n["version"]})
        except api.ApiError as e:
            cards.api_error(e)
            return
        ss.consent_id = r["consent_id"]
        nav.go("kyc")
