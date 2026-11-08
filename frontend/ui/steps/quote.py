import streamlit as st

import api_client as api

from .. import cards, nav
from ..i18n import reason_text, t, unit_word


@st.cache_data(show_spinner=False, ttl=3600)
def catalogue() -> dict[str, dict]:
    return {p["id"]: p for p in api.get("/catalogue")}


def _validate(profile: dict, items: dict[str, int]) -> dict:
    return api.post("/engine/validate", json={"profile": profile, "items": items})


def render() -> None:
    ss = st.session_state
    cards.header(2)
    st.markdown(f"### {t('quote_title')}")
    st.caption(t("quote_sub"))
    if ss.get("partner"):
        st.caption("🤝 " + t("partner_banner", code=ss.partner))
    rec = ss.get("recommendation")
    if not rec:
        st.button(t("back_chat"), key="back_chat_empty", on_click=nav.set_step, args=("chat",))
        return
    try:
        cat = catalogue()
    except api.ApiError as e:
        cards.api_error(e)
        return
    ss.setdefault("bundle_items", {b["id"]: b["qty"] for b in rec["bundle"]})
    ss.setdefault("added", [])
    items: dict[str, int] = {}

    # items from the recommendation + anything the owner added, each with a switch and (per-unit) a quantity
    for pid in list(dict.fromkeys([b["id"] for b in rec["bundle"]] + ss.added)):
        p = cat.get(pid)
        if not p:
            continue
        c1, c2 = st.columns([3, 1.3])
        with c1:
            on = st.toggle(f"**{p['name']}**", value=ss.bundle_items.get(pid, 0) > 0, key=f"tg_{pid}", help=p["description"])
        with c2:
            if p["per_unit"]:
                qty = st.number_input(t("quantity"), min_value=1, max_value=500, value=max(1, ss.bundle_items.get(pid) or 1),
                                      key=f"qty_{pid}", label_visibility="collapsed", disabled=not on)
            else:
                qty = 1
                st.caption(f"₹{p['price_min']:,}/mo")
        st.caption(f"{p['description']} · ₹{p['price_min']:,} {unit_word(p['unit'])}")
        if on:
            items[pid] = int(qty)
    ss.bundle_items = items

    for e in rec.get("excluded", []):
        st.toggle(f"~~{e['name']}~~ · {t('not_available')}", value=False, disabled=True, key=f"ex_{e['id']}")
        st.caption(reason_text(e["reason"], e["why"]))

    try:
        v = _validate(ss.profile, items)
    except api.ApiError as e:
        cards.api_error(e)
        return
    ss.quote = {"items": items, "price": v["price"]}

    with st.expander(t("add_more")):
        for a in v["addable"]:
            if a["eligible"]:
                if st.button(f"➕ {a['name']} · ₹{a['price_min']:,} {unit_word(a['unit'])}", key=f"add_{a['id']}", use_container_width=True):
                    ss.added.append(a["id"])
                    ss.bundle_items[a["id"]] = 1
                    st.rerun()
            else:
                st.caption(f"🔒 {a['name']} — {reason_text(a['reason'], a['reason'].replace('_', ' ').lower())}")

    spend = (ss.profile or {}).get("monthly_spend")
    mn = v["price"]["monthly_min"]
    delta = None
    if spend:
        diff = spend - mn
        delta = (f"{'+' if diff >= 0 else '-'}₹{abs(diff):,} " + t("vs_today", spend=spend))
    st.metric(t("monthly"), f"₹{mn:,}", delta=delta, delta_color="normal")
    st.caption(f"{t('setup')} ₹{v['price']['setup']:,} · {t('contract', n=v['price']['contract_months'])} · {t('install', n=v['price']['install_days'])}")

    if v["violations"]:
        st.warning(t("needs_fix"))
        for x in v["violations"]:
            name = cat.get(x["product_id"], {}).get("name", x["product_id"])
            st.caption(f"❌ {name} — {reason_text(x['reason'], x['detail'])}")
    c1, c2 = st.columns([1, 2])
    with c1:
        st.button(t("back_chat"), key="back_chat", on_click=nav.set_step, args=("chat",), use_container_width=True)
    with c2:
        st.button(t("continue"), key="to_consent", type="primary", use_container_width=True,
                  disabled=bool(v["violations"]) or not items, on_click=nav.set_step, args=("consent",))
