import streamlit as st

import api_client as api

from .. import cards, nav
from ..i18n import t


def _send(text: str) -> None:
    ss = st.session_state
    ss.transcript.append({"role": "user", "text": text})
    with st.chat_message("user"):
        st.markdown(text)
    with st.chat_message("assistant"):
        try:
            with st.spinner(t("thinking")):
                r = api.post("/advisor/chat", json={"session_id": ss.session_id, "text": text})
        except api.ApiError as e:
            cards.api_error(e)
            ss.transcript.pop()
            return
        st.write_stream(cards.stream_text(r["text"]))
    ss.transcript.append({"role": "assistant", "text": r["text"], "provider": r.get("provider")})
    ss.profile = r["profile"]
    ss.missing = r.get("missing", [])
    if r.get("recommendation"):
        ss.recommendation = r["recommendation"]
        ss.explanation = r.get("explanation")
        ss.bundle_items = {b["id"]: b["qty"] for b in r["recommendation"]["bundle"]}   # not `items`: that is a dict method on session_state
    if r.get("language") in ("hi", "en") and r["language"] != ss.lang:
        ss.lang = r["language"]                       # the owner typed in the other script: follow them
    st.rerun()


def render() -> None:
    ss = st.session_state
    cards.header(1)
    for m in ss.transcript:
        with st.chat_message(m["role"]):
            st.markdown(m["text"])
            if m.get("provider") == "offline":
                st.caption(t("offline_note"))
    if ss.get("recommendation"):
        cards.recommendation(ss.recommendation)
        st.button(t("continue_quote"), key="to_quote", type="primary", use_container_width=True, on_click=nav.set_step, args=("quote",))
    elif len(ss.transcript) == 1:
        st.caption(t("try_one"))
        for i in (1, 2, 3):
            ex = t(f"example_{i}")
            if st.button(ex, key=f"example_{i}", use_container_width=True):
                _send(ex)
    if text := st.chat_input(t("ask_placeholder"), key="chat_box"):
        _send(text)
