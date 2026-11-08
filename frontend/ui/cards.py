"""Reusable pieces rendered from engine / API JSON (never from the advisor's prose)."""
import html
import os
import time
from typing import Iterator

import streamlit as st

from .i18n import lang, reason_text, t, unit_word

ICON = {"PASS": "✅", "WARN": "ℹ️", "REVIEW": "⚠️", "FAIL": "❌"}
PILL = {"PASS": "pass", "REVIEW": "review", "FAIL": "fail", "WARN": "info"}


def header(step_index: int | None = None, total: int = 6) -> None:
    st.markdown("<div class='brand'><div class='logo'>A</div><div class='name'>Accel Business</div></div>", unsafe_allow_html=True)
    if step_index is not None:
        dots = "".join(f"<span class='{'done' if i <= step_index else ''}'></span>" for i in range(total))
        st.markdown(f"<div class='steps'>{dots}</div>", unsafe_allow_html=True)


def stream_text(text: str, delay: float | None = None) -> Iterator[str]:
    """Word-by-word generator for st.write_stream (the API returns the whole reply; this just paces it)."""
    delay = float(os.getenv("UI_STREAM_DELAY_S", "0.015")) if delay is None else delay
    for word in text.split(" "):
        yield word + " "
        if delay:
            time.sleep(delay)


def price_block(monthly_from: int, sub: str | None = None) -> None:
    st.markdown(f"<div class='muted'>{t('from')}</div><div class='price'>₹{monthly_from:,}</div>"
                f"<div class='muted'>{sub or t('per_month')}</div>", unsafe_allow_html=True)


def _item_row(name: str, qty: int, unit: str, price_from: int | None, note: str | None = None) -> str:
    qty_txt = t("qty_unit", qty=qty, unit=unit_word(unit, qty)) if qty > 1 or (unit or "").lower().startswith("per ") else ""
    price_txt = t("per_unit_price", p=price_from, unit=unit_word(unit, 1)) if price_from is not None else ""
    note_html = f"<div class='d'>{html.escape(note)}</div>" if note else ""
    return (f"<div class='item'><div><div class='n'>{html.escape(name)} <span class='muted'>{qty_txt}</span></div>{note_html}</div>"
            f"<div class='p'>{price_txt}</div></div>")


def recommendation(rec: dict, notes_detail: list[str] | None = None) -> None:
    """The recommendation card from the engine payload returned by /advisor/chat."""
    with st.container(border=True):
        price_block(rec["monthly_from"])
        st.markdown(f"**{t('your_bundle')}**")
        rows = "".join(_item_row(b["name"], b["qty"], b.get("unit", ""), b.get("price_from_per_unit")) for b in rec["bundle"])
        st.markdown(rows, unsafe_allow_html=True)
        st.caption(f"{t('setup')} ₹{rec['setup_one_time']:,} · {t('contract', n=rec['contract_months'])} · {t('install', n=rec['install_days'])}")
        for n in rec.get("notes") or []:
            st.info(f"{t('added_because')}: {n}", icon="➕")
        if rec.get("excluded"):
            with st.expander(t("left_out")):
                for e in rec["excluded"]:
                    st.markdown(f"• **{html.escape(e['name'])}** — {html.escape(reason_text(e['reason'], e['why']))}", unsafe_allow_html=True)


def verdict_pill(verdict: str) -> None:
    st.markdown(f"<span class='pill {PILL.get(verdict, 'info')}'>{ICON.get(verdict, '')} {t('verdict_' + verdict)}</span>", unsafe_allow_html=True)


def kyc_checks(report: dict) -> None:
    key = "message_hi" if lang() == "hi" else "message_en"
    order = {"FAIL": 0, "REVIEW": 1, "WARN": 2, "PASS": 3}
    checks = sorted(report.get("checks", []), key=lambda c: order.get(c["status"], 9))
    rows = []
    for c in checks:
        ev = f"<div class='ev'>{html.escape(c['evidence'])}</div>" if c.get("evidence") and c["status"] in ("FAIL", "REVIEW") else ""
        rows.append(f"<div class='check'><div class='ic'>{ICON.get(c['status'], '•')}</div><div><div class='msg'>{html.escape(c[key])}</div>{ev}</div></div>")
    st.markdown("".join(rows), unsafe_allow_html=True)
    masked = report.get("masked") or {}
    if masked:
        st.caption(t("masked_ids") + ": " + " · ".join(f"{k.upper()} {v}" for k, v in masked.items()))


def timeline(order: dict) -> None:
    labels = order["labels"]
    cur = order["stage_index"]
    rows = []
    for i, stage in enumerate(order["stages"]):
        cls = "done" if i < cur else ("cur done" if i == cur else "")
        when = order["eta"].get(stage, "")
        eta_txt = t("done_on") if i < cur else t("expected", date=when)
        rows.append(f"<div class='st {cls}'><div class='lab'>{labels[stage][lang()]}</div><div class='eta'>{eta_txt}</div></div>")
    st.markdown(f"<div class='tl'>{''.join(rows)}</div>", unsafe_allow_html=True)


def api_error(e) -> None:
    st.error(getattr(e, "text", lambda: str(e))())
