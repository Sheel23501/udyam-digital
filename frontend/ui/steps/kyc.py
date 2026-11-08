import streamlit as st

import api_client as api

from .. import cards, nav
from ..i18n import lang, t

DOC_TYPES = ("gst_certificate", "udyam_certificate", "signatory_id", "address_proof")


@st.cache_data(show_spinner=False, ttl=3600)
def samples() -> list[str]:
    return [s["applicant"] for s in api.get("/kyc/samples")]


def _run(payload: dict) -> None:
    ss = st.session_state
    try:
        with st.status(t("reading"), expanded=False) as status:
            ss.kyc = api.post("/kyc/run", json=payload)
            status.update(label=t("verdict_" + ss.kyc["verdict"]), state="complete")
    except api.ApiError as e:
        if e.status == 503:
            st.error(t("kyc_unavailable"))
        else:
            cards.api_error(e)
        return
    st.rerun()


def _upload_form() -> None:
    ss = st.session_state
    udyam_only = st.toggle(t("udyam_only"), key="udyam_only")
    files = {}
    for d in DOC_TYPES:
        if udyam_only and d == "gst_certificate":
            continue
        f = st.file_uploader(t(f"doc_{d}"), type=["png", "jpg", "jpeg"], key=f"up_{d}")
        if f is not None:
            files[d] = f
    if st.button(t("verify_docs"), key="verify_upload", type="primary", use_container_width=True):
        if not files:
            st.warning(t("upload_first"))
            return
        try:
            for d, f in files.items():
                api.post("/kyc/upload", data={"session_id": ss.session_id, "doc_type": d}, files={"file": (f.name, f.getvalue(), f.type or "image/png")})
        except api.ApiError as e:
            cards.api_error(e)
            return
        _run({"session_id": ss.session_id, "udyam_only": bool(udyam_only)})


def _sample_form() -> None:
    ss = st.session_state
    try:
        options = samples()
    except api.ApiError as e:
        cards.api_error(e)
        return
    pick = st.selectbox(t("sample_pick"), options, key="sample_pick")
    if st.button(t("verify_docs"), key="verify_sample", type="primary", use_container_width=True):
        _run({"session_id": ss.session_id, "sample_applicant": pick})


def _result(report: dict) -> None:
    ss = st.session_state
    v = report["verdict"]
    with st.container(border=True):
        cards.verdict_pill(v)
        st.write(report["next_step_hi" if lang() == "hi" else "next_step_en"])
        st.markdown(f"**{t('checks')}**")
        cards.kyc_checks(report)
    if v == "PASS":
        if st.button(t("place_order"), key="place_order", type="primary", use_container_width=True):
            try:
                o = api.post("/orders", json={"session_id": ss.session_id, "items": (ss.get("quote") or {}).get("items")})
            except api.ApiError as e:
                cards.api_error(e)
                return
            ss.order_id = o["order_id"]
            nav.go("tracker")
    else:
        c1, c2 = st.columns(2)
        with c1:
            if st.button(t("upload_again") if ss.kyc_mode == "upload" else t("try_another"), key="kyc_again", use_container_width=True):
                ss.pop("kyc", None)
                st.rerun()
        with c2:
            if v == "FAIL" and st.button(t("talk_human"), key="talk_human", use_container_width=True):
                try:
                    api.post("/backoffice/handoff", json={"session_id": ss.session_id, "reason": "KYC failed; owner asked for a human"})
                except api.ApiError as e:
                    cards.api_error(e)
                    return
                ss.handoff = True
                nav.go("done")


def render() -> None:
    ss = st.session_state
    cards.header(4)
    st.markdown(f"### {t('kyc_title')}")
    st.caption(t("kyc_sub"))
    if ss.get("kyc"):
        _result(ss.kyc)
        return
    # the radio is not rendered on the result screen, so Streamlit forgets its widget state; keep the mode in session_state
    labels = [t("kyc_mode_upload"), t("kyc_mode_sample")]
    mode = st.radio("mode", labels, index=1 if ss.get("kyc_mode") == "sample" else 0, horizontal=True,
                    label_visibility="collapsed", key="kyc_mode_radio")
    ss.kyc_mode = "sample" if mode == labels[1] else "upload"
    if ss.kyc_mode == "upload":
        _upload_form()
    else:
        _sample_form()
