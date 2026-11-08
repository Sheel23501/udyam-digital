"""Accel Business — customer journey (phone-shaped). Run: streamlit run frontend/app.py"""
import streamlit as st

import api_client as api
from ui import styles
from ui.i18n import t
from ui.steps import STEPS

st.set_page_config(page_title="Accel Business", page_icon="📶", layout="centered", initial_sidebar_state="collapsed")
styles.inject()

ss = st.session_state
ss.setdefault("step", "language")
ss.setdefault("lang", "hi" if (st.context.locale or "").lower().startswith("hi") else "en")
ss.setdefault("transcript", [])
if "partner" not in ss:
    ss.partner = st.query_params.get("partner")
    ss.ref = st.query_params.get("ref")

if ss.step != "language":
    c1, c2 = st.columns([3, 1.2])
    with c2:
        choice = st.radio(t("lang_label"), ["हिंदी", "English"], index=0 if ss.lang == "hi" else 1, horizontal=True,
                          label_visibility="collapsed", key="lang_radio")
        new = "hi" if choice == "हिंदी" else "en"
        if new != ss.lang:
            ss.lang = new
            st.rerun()

if api.health() is None:
    st.warning(t("backend_down"))
    st.stop()

STEPS[ss.step].render()
