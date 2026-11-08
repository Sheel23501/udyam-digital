"""Back-office: leads the digital journey could not close, scored for the field team; audit log; privacy admin."""
import hmac
import os

import pandas as pd
import streamlit as st

import api_client as api

st.set_page_config(page_title="Accel Business · Back office", page_icon="🗂️", layout="wide")
st.markdown("<style>#MainMenu, footer {visibility:hidden;}</style>", unsafe_allow_html=True)

PIN = os.getenv("STAFF_PIN", "").strip()        # no default PIN: the page stays locked until one is set
ss = st.session_state
if not ss.get("staff_ok"):
    st.title("Back office")
    if not PIN:
        st.error("The back office is locked: no staff PIN is configured. Set STAFF_PIN in .env (local) or in the app's Secrets (Streamlit Cloud).")
        st.stop()
    pin = st.text_input("Staff PIN", type="password", key="staff_pin")
    if st.button("Enter", key="staff_enter", type="primary"):
        if hmac.compare_digest((pin or "").encode(), PIN.encode()):
            ss.staff_ok = True
            st.rerun()
        else:
            st.error("Wrong PIN.")
    st.stop()

if api.health() is None:
    st.error("Backend not reachable")
    st.stop()

st.title("Unclosed leads")
st.caption("Live sessions that stopped before an order, plus a scored sample of historical drops. The score only prioritises outreach; it never denies service.")

tab_queue, tab_detail, tab_audit, tab_admin, tab_system = st.tabs(["Queue", "Lead detail", "Audit log", "Privacy admin", "System"])

with tab_system:
    st.markdown("**Deployment status** — what this running app can see. Key *names* only, never values.")
    st.json(api.health() or {"health": "unreachable"})
    st.json(api.diagnostics())
    st.caption("`advisor_providers` lists the LLM providers with a key. Empty list = no key reached the backend: check the "
               "Secrets in the app settings. Replies marked 'briefly unavailable' with providers present = quota exhausted "
               "(Groq free tier: 200k tokens/day); the quote is still computed by the rules engine.")

with tab_queue:
    c1, c2, c3 = st.columns(3)
    with c1:
        source = st.selectbox("Source", ["all", "session", "lead"], key="f_source")
    with c2:
        min_score = st.slider("Min score", 0.0, 1.0, 0.0, 0.05, key="f_score")
    with c3:
        limit = st.selectbox("Rows", [50, 100, 200, 500], index=2, key="f_limit")
    try:
        rows = api.get("/backoffice/leads", limit=limit)
    except api.ApiError as e:
        st.error(e.text())
        st.stop()
    df = pd.DataFrame(rows)
    if source != "all":
        df = df[df["source"] == source]
    df = df[df["score"] >= min_score]
    partners = ["all"] + sorted({p for p in df["partner"].dropna().unique()}) if "partner" in df else ["all"]
    partner = st.selectbox("Partner", partners, key="f_partner")
    if partner != "all":
        df = df[df["partner"] == partner]
    st.caption(f"{len(df)} leads · total est. value ₹{int(df['est_monthly_value'].sum()):,}/month")
    st.dataframe(
        df[["id", "source", "business", "segment", "city", "language", "est_monthly_value", "last_step", "reason", "score", "suggested_action", "partner", "date"]],
        use_container_width=True, hide_index=True, height=520,
        column_config={
            "est_monthly_value": st.column_config.NumberColumn("Value ₹/mo", format="₹%d"),
            "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=1, format="%.2f"),
            "suggested_action": st.column_config.TextColumn("Next action", width="large"),
            "reason": st.column_config.TextColumn("Why it stopped", width="medium"),
        },
    )

with tab_detail:
    lead_id = st.text_input("Lead or session id", key="detail_id", placeholder="L00001 or a session id from the queue")
    if lead_id:
        try:
            d = api.get(f"/backoffice/leads/{lead_id.strip()}/score")
        except api.ApiError as e:
            st.error(e.text())
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Score", f"{d['score']:.2f}")
            c2.metric("Est. value", f"₹{d['est_monthly_value']:,}/mo")
            c3.metric("Stopped at", d.get("last_step") or "-")
            st.markdown(f"**{d.get('business') or ''}** · {d.get('city') or ''} · {d.get('reason') or ''}")
            st.markdown("**Why this score**")
            for r in d["reasons"]:
                st.markdown(f"- {r}")
            st.info(f"Suggested: {d['suggested_action']}")
            partner = st.selectbox("Assign to partner", ["—", "P-DEL-01", "P-MUM-04", "P-BLR-02", "P-PUN-03"], key="assign_partner")
            if st.button("Assign", key="assign_btn") and partner != "—":
                st.success(f"Assigned {lead_id} to {partner} (demo: assignment is not persisted)")

with tab_audit:
    try:
        audit = api.get("/backoffice/audit", limit=200)
    except api.ApiError as e:
        st.error(e.text())
    else:
        st.caption("Every lookup, KYC run, consent and admin action. Subjects are masked before they are written.")
        st.dataframe(pd.DataFrame(audit), use_container_width=True, hide_index=True, height=480)

with tab_admin:
    st.markdown("**Retention purge** — deletes uploaded images for rejected applications older than 30 days and verified ones older than 90 days.")
    c1, c2 = st.columns(2)
    rej = c1.number_input("Rejected: days", 0, 365, 30, key="ret_rej")
    ver = c2.number_input("Verified: days", 0, 365, 90, key="ret_ver")
    if st.button("Run retention purge", key="run_retention", type="primary"):
        try:
            r = api.post("/admin/retention/run", json={"rejected_days": int(rej), "verified_days": int(ver)})
        except api.ApiError as e:
            st.error(e.text())
        else:
            st.success(f"Removed {len(r['removed'])} folder(s), {r['files']} file(s), {r['bytes']:,} bytes; kept {r['kept']}.")
            if r["removed"]:
                st.dataframe(pd.DataFrame(r["removed"]), hide_index=True, use_container_width=True)
    st.divider()
    st.markdown("**Erasure request** — a data principal asks us to delete their data: images and transcript go now; only the regulatory KYC record stays.")
    sid = st.text_input("Session id", key="erase_sid")
    if st.button("Erase", key="erase_btn") and sid:
        try:
            r = api.post(f"/admin/erase/{sid.strip()}")
        except api.ApiError as e:
            st.error(e.text())
        else:
            st.success(f"Erased: {r['images_deleted']} image(s), transcript deleted, KYC record kept.")
