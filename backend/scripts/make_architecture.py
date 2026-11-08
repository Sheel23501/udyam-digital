#!/usr/bin/env python
"""Architecture diagram (PNG) for the deck and README, drawn from the same boxes as docs/architecture.md.

Usage: python scripts/make_architecture.py   -> docs/architecture.png
Canvas units are inches (16 x 9), so widths below are literal inches at any dpi."""
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "architecture.png"
INK, INK2, MUTED, SURFACE = "#0b0b0b", "#52514e", "#898781", "#fcfcfb"
BLUE, ORANGE, AQUA, YELLOW, BRAND = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#E40046"
W, H = 16.0, 9.0
BOX_W, HEAD, LINE, PAD = 3.15, 0.46, 0.33, 0.28


def box(ax, x, y, title, lines, color, title_color="#ffffff", w=BOX_W):
    """Box whose height follows its content. Returns (x, y, w, h)."""
    h = HEAD + LINE * len(lines) + PAD
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.0,rounding_size=0.14", linewidth=1.3, facecolor="#ffffff",
                                edgecolor=color, zorder=2))
    ax.add_patch(FancyBboxPatch((x, y + h - HEAD), w, HEAD, boxstyle="round,pad=0.0,rounding_size=0.14", linewidth=0,
                                facecolor=color, zorder=3))
    ax.add_patch(plt.Rectangle((x, y + h - HEAD), w, HEAD / 2, facecolor=color, linewidth=0, zorder=3))   # square the header's bottom
    ax.text(x + w / 2, y + h - HEAD / 2, title, ha="center", va="center", fontsize=10.5, fontweight="bold", color=title_color, zorder=4)
    for i, line in enumerate(lines):
        ax.text(x + 0.16, y + h - HEAD - 0.22 - i * LINE, line, ha="left", va="center", fontsize=9, color=INK2, zorder=4)
    return x, y, w, h


def arrow(ax, p, q, label=None, color=MUTED, ls="-", label_dy=0.0, at=0.5):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=13, linewidth=1.3, color=color, linestyle=ls, zorder=1,
                                 shrinkA=0, shrinkB=0))
    if label:
        mx, my = p[0] + (q[0] - p[0]) * at, p[1] + (q[1] - p[1]) * at + label_dy
        ax.text(mx, my, label, ha="center", va="center", fontsize=8.2, color=INK2, zorder=5,
                bbox={"boxstyle": "round,pad=0.18", "facecolor": SURFACE, "edgecolor": "none"})


def main() -> int:
    fig, ax = plt.subplots(figsize=(W, H), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax.text(0.5, 8.6, "Udyam Digital: rules decide, the LLM narrates, consent gates every document", fontsize=16, fontweight="bold", color=INK, va="center")
    ax.text(0.5, 8.2, "Phone-first Streamlit journey on a FastAPI service · deterministic rules engine · Smart KYC with vision extraction and registry checks · DPDP plumbing throughout",
            fontsize=9.8, color=INK2, va="center")

    # columns: 0.5 | 4.45 | 8.4 | 12.35   (box width 3.15, gaps 0.8)
    phone = box(ax, 0.5, 4.5, "Owner's phone · Streamlit UI", ["language → OTP → advisor chat", "card rendered from engine JSON",
                "quote toggles, re-validated live", "consent → KYC upload / sample", "tracker · back-office (staff PIN)"], BRAND)
    api = box(ax, 4.45, 4.5, "FastAPI", ["/sessions  /advisor/chat", "/engine/recommend  /validate", "/consent  /kyc/*  /lookup/*",
              "/orders  /backoffice/*", "/admin/retention  /admin/erase"], BLUE)
    engine = box(ax, 8.4, 6.05, "Rules engine (deterministic)", ["eligibility: tier · staff · sites · GST status",
                 "dependency closure (requires_one_of)", "price · validate on every toggle"], BLUE)
    advisor = box(ax, 8.4, 3.6, "Advisor (the LLM only narrates)", ["OpenAI-compatible provider chain", "Groq → Cerebras → Mistral → Gemini",
                  "tools: update_profile · get_recommendation", "offline fallback: rules + engine text"], ORANGE)
    kyc = box(ax, 8.4, 1.15, "Smart KYC", ["image gates: blur · skew · size", "vision extraction → Pydantic schema",
              "12 validators: checksum · registry · dates", "names · signatory · address recency"], AQUA)
    db = box(ax, 12.35, 4.5, "SQLite, built from the 4 CSVs", ["product_catalogue · smb_leads", "mock GSTIN / Udyam registries",
             "sessions · consents · kyc_applications", "orders · audit_log (masked)"], MUTED)
    ext = box(ax, 12.35, 1.15, "Outside the boundary", ["LLM API: business facts only", "Vision API: document image only",
              "nothing leaves before consent; no CRM data", "prod: GSTN · Udyam · DigiLocker · eSign"], YELLOW, title_color="#0b0b0b")

    def right(b):
        return b[0] + b[2]

    def mid_y(b):
        return b[1] + b[3] / 2

    arrow(ax, (right(phone), mid_y(phone)), (api[0], mid_y(api)), "HTTP or\nin-process", label_dy=0.32)
    arrow(ax, (right(api), api[1] + api[3] - 0.5), (engine[0], mid_y(engine)), "profile\n→ bundle", at=0.45, label_dy=0.0)
    arrow(ax, (right(api), mid_y(api)), (advisor[0], mid_y(advisor)), "chat\nturn", at=0.5)
    arrow(ax, (right(api), api[1] + 0.4), (kyc[0], mid_y(kyc)), "images,\nafter\nconsent", at=0.5)
    arrow(ax, (advisor[0] + 1.2, advisor[1] + advisor[3]), (advisor[0] + 1.2, engine[1]), "tool calls", color=ORANGE)
    arrow(ax, (right(engine), mid_y(engine)), (db[0], db[1] + db[3] - 0.4), "read /\nwrite", at=0.5)
    arrow(ax, (right(advisor), advisor[1] + 0.5), (ext[0], ext[1] + ext[3] - 0.3), "facts\nonly", color=ORANGE, at=0.75)
    arrow(ax, (right(kyc), kyc[1] + 0.6), (ext[0], ext[1] + 0.6), "image\nonly", color=AQUA, label_dy=0.3)
    arrow(ax, (right(kyc), kyc[1] + kyc[3] - 0.3), (db[0], db[1] + 0.5), "registry\nlookups", color=AQUA, ls=(0, (3, 2)), at=0.22)

    # privacy strip
    ax.add_patch(FancyBboxPatch((0.5, 0.15), 15.0, 0.8, boxstyle="round,pad=0.0,rounding_size=0.14", linewidth=1.3,
                                facecolor="#ffffff", edgecolor=BRAND, zorder=2))
    ax.text(0.7, 0.72, "DPDP plumbing (backend/app/privacy/)", fontsize=10, fontweight="bold", color=BRAND, va="center", zorder=4)
    ax.text(0.7, 0.4, "itemised consent before any document (API returns 403 otherwise) · identifiers masked in UI, API and audit log · retention purge 30 d rejected / 90 d verified · "
            "erasure keeps only the regulatory KYC record · REVIEW before any adverse decision", fontsize=8.8, color=INK2, va="center", zorder=4)
    fig.savefig(OUT, facecolor=SURFACE)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
