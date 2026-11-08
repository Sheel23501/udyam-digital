#!/usr/bin/env python
"""Charts for the deck, computed from smb_leads.csv (never typed by hand). Writes PNGs + numbers.json + README.md to docs/charts/.

Usage: python scripts/make_charts.py            (needs matplotlib: pip install matplotlib)

Design rules applied (dataviz method): one axis per chart, categorical colours in a fixed validated order, thin marks,
recessive grid, selective direct labels, text in ink colours (never the series colour), a legend whenever >= 2 series."""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import DATA_DIR  # noqa: E402
from app.engine.catalogue import catalogue  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "charts"

# validated palette (reference instance of the dataviz skill) + brand highlight
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
BRAND = "#E40046"
SURFACE, INK, INK2, MUTED, GRID, BASE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "axes.titlesize": 14, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.titlepad": 14, "axes.labelcolor": INK2, "axes.edgecolor": BASE, "axes.linewidth": 0.8, "xtick.color": MUTED, "ytick.color": INK2,
    "xtick.labelsize": 10, "ytick.labelsize": 10.5, "axes.grid": False, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "savefig.dpi": 200, "figure.figsize": (10, 5.6), "text.color": INK,
})


def _frame(ax, grid_axis: str = "x") -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(BASE)
    ax.spines["bottom"].set_color(BASE)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def _finish(fig, ax, title: str, sub: str, name: str, source: str, left: float | None = None, bottom: float = 0.11) -> None:
    """Title and subtitle as figure text aligned with the plot's left edge; the left margin grows with the longest
    y tick label so horizontal-bar categories are never clipped."""
    if left is None:
        longest = max((len(t.get_text()) for t in ax.get_yticklabels()), default=0)
        left = min(0.40, 0.07 + 0.0068 * longest) if longest > 6 else 0.07
    import textwrap
    width_in = fig.get_size_inches()[0] * (0.97 - left)
    title = textwrap.fill(title, max(30, int(width_in * 9.5)))          # ~9.5 bold 14pt chars per inch
    sub = textwrap.fill(sub, max(40, int(width_in * 13.5)))
    top = 0.82 - 0.035 * (title.count("\n") + sub.count("\n"))
    fig.subplots_adjust(left=left, right=0.97, top=top, bottom=bottom)
    fig.text(left, 0.945, title, fontsize=14, fontweight="bold", color=INK, va="top", linespacing=1.25)
    fig.text(left, 0.945 - 0.055 * (title.count("\n") + 1), sub, color=INK2, fontsize=10.5, va="top", linespacing=1.3)
    fig.text(left, 0.015, source, color=MUTED, fontsize=8.5)
    fig.savefig(OUT / name)
    plt.close(fig)


def load() -> pd.DataFrame:
    df = pd.read_csv(Path(DATA_DIR) / "smb_leads.csv", dtype=str, keep_default_na=False)
    for c in ("employee_count", "num_sites", "monthly_telecom_spend_inr", "customer_follow_up_calls", "days_lead_to_activation",
              "monthly_bundle_value_inr", "acquisition_cost_inr"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["activated"] = df["outcome"].eq("Activated")
    df["churned"] = df["churned_within_6_months"].isin(["Y", "True", "true", "1"])
    return df


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    df = load()
    cat = catalogue()
    lo, hi = df["created_date"].min(), df["created_date"].max()
    source = f"Source: smb_leads.csv, {len(df):,} leads created {lo} to {hi}. Computed by scripts/make_charts.py."
    numbers: dict = {"leads": int(len(df)), "activated": int(df["activated"].sum()), "period": [lo, hi]}

    # 1. activation by lead source
    g = df.groupby("lead_source").agg(n=("lead_id", "size"), rate=("activated", "mean")).sort_values("rate")
    numbers["activation_by_source"] = {k: {"rate_pct": round(v.rate * 100, 1), "leads": int(v.n)} for k, v in g.iterrows()}
    fig, ax = plt.subplots()
    colors = [BRAND if s == "Referral" else BLUE for s in g.index]
    ax.barh(g.index, g["rate"] * 100, color=colors, height=0.58)
    for i, (n, r) in enumerate(zip(g["n"], g["rate"])):
        ax.text(r * 100 + 0.25, i, f"{r * 100:.1f}%  ({n:,} leads)", va="center", color=INK2, fontsize=10)
    ax.set_xlim(0, g["rate"].max() * 100 * 1.35)
    ax.set_xlabel("Leads that activated (%)")
    _frame(ax, "x")
    _finish(fig, ax, "Referrals convert 2× field sales and 5× WhatsApp campaigns",
            "Activation rate by lead source. Referral highlighted.", "01_activation_by_source.png", source)

    # 2. payback by segment: blended CAC per activation / monthly bundle value
    rows = []
    for seg, d in df.groupby("segment"):
        acts = d[d["activated"]]
        cac = d["acquisition_cost_inr"].sum() / max(1, len(acts))
        value = acts["monthly_bundle_value_inr"].mean()
        churn = acts["churned"].mean() * 100
        rows.append((seg, cac, value, cac / value if value else float("nan"), churn, len(acts)))
    pb = pd.DataFrame(rows, columns=["segment", "cac", "value", "payback", "churn", "acts"]).sort_values("payback")
    numbers["payback_by_segment"] = {r.segment: {"blended_cac": round(r.cac), "monthly_value": round(r.value), "payback_months": round(r.payback, 1),
                                                 "churn_6m_pct": round(r.churn, 1), "activations": int(r.acts)} for r in pb.itertuples()}
    micro_fs = df[(df["segment"] == "Micro retail & services") & (df["lead_source"] == "Field sales")]
    numbers["micro_retail_field_sales"] = {"blended_cac": round(micro_fs["acquisition_cost_inr"].sum() / max(1, micro_fs["activated"].sum())),
                                           "monthly_value": round(micro_fs[micro_fs["activated"]]["monthly_bundle_value_inr"].mean()),
                                           "activations": int(micro_fs["activated"].sum()), "leads": int(len(micro_fs))}
    fig, ax = plt.subplots()
    ax.barh(pb["segment"], pb["payback"], color=BLUE, height=0.58)
    for i, r in enumerate(pb.itertuples()):
        ax.text(r.payback + 0.15, i, f"{r.payback:.1f} months", va="center", color=INK, fontsize=11, fontweight="bold")
        ax.text(r.payback + 0.15, i + 0.3, f"CAC ₹{r.cac:,.0f} → ₹{r.value:,.0f}/month · churn {r.churn:.0f}%",
                va="center", color=INK2, fontsize=9)
    ax.set_xlim(0, pb["payback"].max() * 1.6)
    ax.set_xlabel("Months of revenue to repay the acquisition cost")
    _frame(ax, "x")
    _finish(fig, ax, "Micro retail pays back in 8 months; multi-site and manufacturers in about one",
            "Blended CAC per activation (all leads' acquisition cost ÷ activations) over monthly bundle value, by segment.",
            "02_payback_by_segment.png", source)

    # 3. drop reasons, grouped
    GROUPS = {
        "Sales process / human in the way": (ORANGE, ["Unreachable after 3 attempts", "Owner had no time for a visit", "Visit not scheduled by sales",
                                                      "Quote took too long to arrive", "Quote too complex to understand", "Authorised signatory not available",
                                                      "Found paperwork too long", "Installation delayed beyond 21 days"]),
        "Offer / price / fit": (BLUE, ["Not interested on first call", "Only wanted a mobile plan", "Locked in with current provider", "Decided to wait",
                                       "Site not feasible for fibre", "Competitor offered cheaper plan", "Price too high"]),
        "Paperwork / data quality": (AQUA, ["Missing GST or Udyam document", "Document details did not match", "First payment failed",
                                           "Customer cancelled before install", "Wrong or invalid number"]),
    }
    dr = df[~df["activated"]]["drop_reason"].value_counts()
    numbers["drop_reasons"] = {k: int(v) for k, v in dr.items()}
    group_of = {r: g for g, (_, rs) in GROUPS.items() for r in rs}
    numbers["drop_groups"] = {g: int(sum(dr.get(r, 0) for r in rs)) for g, (_, rs) in GROUPS.items()}
    fig, ax = plt.subplots(figsize=(10, 7))
    order = dr.sort_values()
    ax.barh(order.index, order.values, color=[GROUPS[group_of.get(r, "Offer / price / fit")][0] for r in order.index], height=0.6)
    for i, v in enumerate(order.values):
        ax.text(v + 6, i, f"{v:,}", va="center", color=INK2, fontsize=9.5)
    ax.set_xlim(0, order.max() * 1.15)
    ax.set_xlabel("Dropped leads")
    _frame(ax, "x")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c, _ in GROUPS.values()]
    ax.legend(handles, [f"{g}  ({numbers['drop_groups'][g]:,})" for g in GROUPS], loc="lower right", frameon=False, fontsize=9.5, labelcolor=INK2)
    total = int(dr.sum())
    share = numbers["drop_groups"]["Sales process / human in the way"] / total * 100
    _finish(fig, ax, f"{share:.0f}% of drops are the sales process itself, not the offer",
            f"Why {total:,} leads dropped, grouped. A self-serve journey removes the orange bars.", "03_drop_reasons.png", source)
    numbers["human_in_the_way_pct"] = round(share, 1)

    # 4. GST divider
    gst = df.groupby("has_gstin").agg(n=("lead_id", "size"), rate=("activated", "mean"))
    gst_only = {"P03", "P05", "P06", "P10", "P12", "P13", "P14", "P15", "P21", "P24"}
    asked_gst_only = df[(df["has_gstin"] == "N") & df["products_of_interest"].apply(lambda s: bool(set(s.split(";")) & gst_only))]
    numbers["gst"] = {"with_gst_rate_pct": round(gst.loc["Y", "rate"] * 100, 1), "without_gst_rate_pct": round(gst.loc["N", "rate"] * 100, 1),
                      "with_gst_leads": int(gst.loc["Y", "n"]), "without_gst_leads": int(gst.loc["N", "n"]),
                      "no_gst_asked_gst_only_products": int(len(asked_gst_only)), "their_rate_pct": round(asked_gst_only["activated"].mean() * 100, 1)}
    fig, ax = plt.subplots(figsize=(10, 5.2))
    labels = [f"GST registered\n({gst.loc['Y', 'n']:,} leads)", f"No GST\n({gst.loc['N', 'n']:,} leads)"]
    vals = [gst.loc["Y", "rate"] * 100, gst.loc["N", "rate"] * 100]
    ax.bar(labels, vals, color=[BLUE, BLUE], width=0.45)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.3, f"{v:.1f}%", ha="center", color=INK, fontsize=12, fontweight="bold")
    ax.set_ylim(0, max(vals) * 1.45)
    ax.set_ylabel("Leads that activated (%)")
    _frame(ax, "y")
    ax.annotate(f"{len(asked_gst_only)} no-GST leads asked for GST-only products\n→ {asked_gst_only['activated'].mean() * 100:.1f}% activated. "
                "The journey needs a GST-free path.", xy=(1, vals[1]), xytext=(0.52, max(vals) * 1.15), color=INK2, fontsize=10,
                arrowprops={"arrowstyle": "-", "color": BASE})
    _finish(fig, ax, "GST registration is the great divider: 5× the activation rate",
            "Activation rate by GST status.", "04_gst_divider.png", source)

    # 5. asked vs sold
    pids = ["P04", "P18", "P14", "P15", "P23", "P19"]
    asked = {p: int(df["products_of_interest"].str.contains(p).sum()) for p in pids}
    sold = {p: int(df[df["activated"]]["bundle_products"].str.contains(p).sum()) for p in pids}
    numbers["asked_vs_sold"] = {p: {"name": cat[p].name, "asked": asked[p], "sold": sold[p]} for p in pids}
    fig, ax = plt.subplots()
    x = range(len(pids))
    w = 0.38
    ax.bar([i - w / 2 for i in x], [asked[p] for p in pids], width=w, color=BLUE, label="Asked for (products of interest)")
    ax.bar([i + w / 2 for i in x], [sold[p] for p in pids], width=w, color=ORANGE, label="Sold (in an activated bundle)")
    for i, p in enumerate(pids):
        ax.text(i - w / 2, asked[p] + 8, f"{asked[p]}", ha="center", color=INK2, fontsize=9.5)
        ax.text(i + w / 2, sold[p] + 8, f"{sold[p]}", ha="center", color=INK2, fontsize=9.5)
    import textwrap
    ax.set_xticks(list(x), [textwrap.fill(cat[p].name, 15) + f"\n({p})" for p in pids], fontsize=9)
    ax.set_ylabel("Leads")
    ax.set_ylim(0, max(asked.values()) * 1.22)
    ax.legend(frameon=False, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.02), labelcolor=INK2, fontsize=10)
    _frame(ax, "y")
    _finish(fig, ax, "What owners ask for is not what sales sells",
            "Products named in leads' interests vs products in activated bundles.", "05_asked_vs_sold.png", source, bottom=0.2)

    # 6. lead to activation days
    days = df[df["activated"]]["days_lead_to_activation"].dropna()
    numbers["days_to_activation"] = {"median": float(days.median()), "mean": round(float(days.mean()), 1), "min": int(days.min()), "max": int(days.max())}
    fig, ax = plt.subplots()
    bins = range(int(days.min()), int(days.max()) + 2)
    ax.hist(days, bins=bins, color=BLUE, rwidth=0.86)
    ax.axvline(days.median(), color=INK, linewidth=1.2, linestyle="--")
    ax.text(days.median() + 0.3, ax.get_ylim()[1] * 0.92, f"median {days.median():.0f} days", color=INK, fontsize=10)
    ax.axvspan(0, 5, color=AQUA, alpha=0.15)
    ax.text(2.5, ax.get_ylim()[1] * 0.92, "target\n≤ 5 days", ha="center", color=INK2, fontsize=9.5)
    ax.set_xlabel("Days from lead to activation")
    ax.set_ylabel("Activated customers")
    _frame(ax, "y")
    _finish(fig, ax, f"Today a lead takes {days.median():.0f} days to become a customer",
            "Distribution of lead-to-activation time for activated leads; the digital journey targets install-bound ≤ 5 days.",
            "06_days_to_activation.png", source)

    # 7. churn vs follow-up calls
    acts = df[df["activated"]].copy()
    acts["calls"] = acts["customer_follow_up_calls"].fillna(0).astype(int).clip(upper=5)
    ch = acts.groupby("calls").agg(n=("lead_id", "size"), churn=("churned", "mean"))
    numbers["churn_by_follow_up_calls"] = {int(k): {"customers": int(v.n), "churn_6m_pct": round(v.churn * 100, 1)} for k, v in ch.iterrows()}
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.bar([str(c) if c < 5 else "5+" for c in ch.index], ch["churn"] * 100, color=BLUE, width=0.5)
    for i, (n, c) in enumerate(zip(ch["n"], ch["churn"])):
        ax.text(i, c * 100 + 0.6, f"{c * 100:.0f}%  (n={n})", ha="center", color=INK2, fontsize=9.5)
    ax.set_xlabel("Status / follow-up calls the customer had to make")
    ax.set_ylabel("Churned within 6 months (%)")
    ax.set_ylim(0, ch["churn"].max() * 100 * 1.3)
    _frame(ax, "y")
    _finish(fig, ax, "Every status call a customer has to make predicts churn",
            "6-month churn among activated customers by number of follow-up calls. The tracker exists to make this zero.",
            "07_churn_vs_calls.png", source)

    # 8. language mix
    lang = df["preferred_language"].value_counts(normalize=True).sort_values() * 100
    numbers["language_share_pct"] = {k: round(v, 1) for k, v in lang.items()}
    fig, ax = plt.subplots()
    covered = {"Hindi", "English"}
    ax.barh(lang.index, lang.values, color=[BLUE if k in covered else BASE for k in lang.index], height=0.6)
    for i, v in enumerate(lang.values):
        ax.text(v + 0.4, i, f"{v:.1f}%", va="center", color=INK2, fontsize=9.5)
    ax.set_xlim(0, lang.max() * 1.25)
    ax.set_xlabel("Share of leads (%)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=BLUE), plt.Rectangle((0, 0), 1, 1, color=BASE)]
    ax.legend(handles, ["Covered by the Hindi / English / Hinglish journey", "Regional: English UI + offer of Hindi/English"],
              loc="lower right", frameon=False, fontsize=9.5, labelcolor=INK2)
    _frame(ax, "x")
    cov = lang.get("Hindi", 0) + lang.get("English", 0)
    numbers["language_covered_pct"] = round(cov, 1)
    _finish(fig, ax, f"Hindi + English cover {cov:.0f}% of leads; the rest are 8 regional languages",
            "Preferred language of leads. Supporting two languages well beats ten badly.", "08_language_mix.png", source)

    (OUT / "numbers.json").write_text(json.dumps(numbers, indent=2, ensure_ascii=False), encoding="utf-8")
    readme = ["# Charts for the deck", "", f"Generated from `backend/data/smb_leads.csv` by `backend/scripts/make_charts.py` ({len(df):,} leads, {lo} to {hi}).",
              "Every number below is in `numbers.json`; regenerate with `python scripts/make_charts.py` from `backend/`.", "",
              "| Chart | Headline | Use on slide |", "|---|---|---|",
              f"| 01_activation_by_source | Referral {numbers['activation_by_source']['Referral']['rate_pct']}% vs field sales {numbers['activation_by_source']['Field sales']['rate_pct']}% vs WhatsApp campaign {numbers['activation_by_source']['WhatsApp campaign']['rate_pct']}% | Problem / where to acquire |",
              f"| 02_payback_by_segment | Micro retail payback {numbers['payback_by_segment']['Micro retail & services']['payback_months']} months; multi-site {numbers['payback_by_segment']['Small multi-site businesses']['payback_months']}; manufacturers {numbers['payback_by_segment']['Small manufacturers']['payback_months']} | Business case / redeploy field force |",
              f"| 03_drop_reasons | {numbers['human_in_the_way_pct']}% of drops are the sales process | Problem |",
              f"| 04_gst_divider | {numbers['gst']['with_gst_rate_pct']}% vs {numbers['gst']['without_gst_rate_pct']}%; {numbers['gst']['no_gst_asked_gst_only_products']} no-GST leads asked for GST-only products ({numbers['gst']['their_rate_pct']}%) | Why the engine has a GST-free path |",
              f"| 05_asked_vs_sold | AirFiber asked {numbers['asked_vs_sold']['P04']['asked']}× sold {numbers['asked_vs_sold']['P04']['sold']}×; WhatsApp API {numbers['asked_vs_sold']['P15']['asked']}/{numbers['asked_vs_sold']['P15']['sold']} | Advisor sells what is asked, within rules |",
              f"| 06_days_to_activation | median {numbers['days_to_activation']['median']:.0f} days today → target ≤ 5 | Tracker / instant quote |",
              f"| 07_churn_vs_calls | churn {numbers['churn_by_follow_up_calls'][1]['churn_6m_pct']}% at 1 call → {numbers['churn_by_follow_up_calls'][5]['churn_6m_pct']}% at 5+ | Why the tracker matters |",
              f"| 08_language_mix | Hindi + English = {numbers['language_covered_pct']}% | Language scope decision |",
              "", f"Micro retail via field sales: blended CAC ₹{numbers['micro_retail_field_sales']['blended_cac']:,} per activation for ₹{numbers['micro_retail_field_sales']['monthly_value']:,}/month "
              f"({numbers['micro_retail_field_sales']['activations']} activations from {numbers['micro_retail_field_sales']['leads']:,} leads)."]
    (OUT / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(f"wrote 8 charts, numbers.json and README.md to {OUT}")
    print(json.dumps({k: numbers[k] for k in ("human_in_the_way_pct", "gst", "micro_retail_field_sales", "days_to_activation", "language_covered_pct")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
