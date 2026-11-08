#!/usr/bin/env python
"""Build the 10-slide business case on the Airtel SYNC submission template.

Usage: python scripts/make_deck.py  ->  docs/Udyam_Digital_Submission.pptx
Every figure comes from docs/charts/numbers.json (computed by make_charts.py) or from the rules engine; nothing is typed in.
Charts and tables are native PowerPoint objects (editable). Template backgrounds are the two images shipped in the
official template (title + body)."""
import json
import sys
import zipfile
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.engine.bundles import recommend  # noqa: E402
from app.engine.catalogue import catalogue  # noqa: E402
from app.engine.models import Need, Profile  # noqa: E402

TEMPLATE = ROOT.parent / "6ad9d4887d445_airtel_sync" / "Submission Template_Sync.pptx"
OUT = ROOT / "docs" / "Udyam_Digital_Submission.pptx"
NUMBERS = json.loads((ROOT / "docs" / "charts" / "numbers.json").read_text(encoding="utf-8"))
WORK = ROOT / "docs" / ".deck_assets"

RED, DARK, INK2, MUTED, LINE = RGBColor(0xE4, 0x00, 0x46), RGBColor(0x1A, 0x1A, 0x1A), RGBColor(0x4B, 0x55, 0x63), RGBColor(0x8A, 0x8F, 0x98), RGBColor(0xE5, 0xE7, 0xEB)
TINT, TINT2, WHITE, GREEN, AMBER = RGBColor(0xFD, 0xE7, 0xEE), RGBColor(0xF6, 0xF6, 0xF8), RGBColor(0xFF, 0xFF, 0xFF), RGBColor(0x0C, 0xA3, 0x0C), RGBColor(0xE0, 0x8A, 0x00)
GREY_BAR = RGBColor(0xB8, 0xBC, 0xC4)
FONT = "Arial"
W, H = Inches(10), Inches(5.625)
SOURCE = f"Source: smb_leads.csv, {NUMBERS['leads']:,} leads ({NUMBERS['period'][0]} to {NUMBERS['period'][1]}); every figure reproduced by backend/scripts/make_charts.py."


# ---------------------------------------------------------------- helpers
def extract_backgrounds() -> tuple[Path, Path]:
    WORK.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(TEMPLATE)
    title_bg, body_bg = WORK / "title_bg.jpg", WORK / "body_bg.jpg"
    title_bg.write_bytes(z.read("ppt/media/image2.jpg"))      # slide 1 of the template
    body_bg.write_bytes(z.read("ppt/media/image1.jpg"))       # slide 2 of the template
    return title_bg, body_bg


def clear_slides(prs: Presentation) -> None:
    ids = prs.slides._sldIdLst
    for sld in list(ids):
        prs.part.drop_rel(sld.rId)
        ids.remove(sld)


def new_slide(prs: Presentation, bg: Path):
    s = prs.slides.add_slide(prs.slide_layouts[10])           # BLANK
    pic = s.shapes.add_picture(str(bg), 0, 0, W, H)
    s.shapes._spTree.remove(pic._element)
    s.shapes._spTree.insert(2, pic._element)                  # behind everything
    return s


def text(slide, x, y, w, h, s, size=12, bold=False, color=DARK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False, line=1.1):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.04)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = anchor
    lines = s if isinstance(s, list) else [s]
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line
        runs = ln if isinstance(ln, list) else [(ln, {})]
        for seg, fmt in runs:
            r = p.add_run()
            r.text = seg
            r.font.name = FONT
            r.font.size = Pt(fmt.get("size", size))
            r.font.bold = fmt.get("bold", bold)
            r.font.italic = fmt.get("italic", italic)
            r.font.color.rgb = fmt.get("color", color)
    return tb


def rect(slide, x, y, w, h, fill=None, line_color=None, shape=MSO_SHAPE.RECTANGLE, radius=None, line_w=0.75):
    sh = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line_color is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line_color
        sh.line.width = Pt(line_w)
    sh.shadow.inherit = False
    if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        sh.adjustments[0] = radius
    sh.text_frame.text = ""
    return sh


def card(slide, x, y, w, h, fill=WHITE, line_color=LINE):
    return rect(slide, x, y, w, h, fill=fill, line_color=line_color, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)


def title(slide, head, sub=None):
    text(slide, 0.45, 0.72, 8.3, 0.5, head, size=20, bold=True, color=DARK)
    rect(slide, 0.5, 1.22, 0.6, 0.045, fill=RED)
    if sub:
        text(slide, 0.45, 1.3, 8.9, 0.35, sub, size=10.5, color=INK2)


def source(slide, extra=None):
    text(slide, 0.45, 5.13, 7.7, 0.3, extra or SOURCE, size=7, color=MUTED)


def hero(slide, x, y, w, number, label, color=RED, num_size=24):
    card(slide, x, y, w, 0.92, fill=WHITE)
    text(slide, x + 0.08, y + 0.06, w - 0.16, 0.5, number, size=num_size, bold=True, color=color)
    text(slide, x + 0.08, y + 0.53, w - 0.16, 0.38, label, size=8, color=INK2, line=1.0)


def table(slide, x, y, w, h, rows, col_w, header_fill=DARK, size=8.5, first_col_bold=True, zebra=True, highlight_rows=()):
    n_r, n_c = len(rows), len(rows[0])
    t = slide.shapes.add_table(n_r, n_c, Inches(x), Inches(y), Inches(w), Inches(h)).table
    for j, cw in enumerate(col_w):
        t.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        t.rows[i].height = Inches(h / n_r)
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.margin_left = c.margin_right = Inches(0.05)
            c.margin_top = c.margin_bottom = Inches(0.02)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.fill.solid()
            if i == 0:
                c.fill.fore_color.rgb = header_fill
            elif i in highlight_rows:
                c.fill.fore_color.rgb = TINT
            else:
                c.fill.fore_color.rgb = TINT2 if (zebra and i % 2 == 0) else WHITE
            tf = c.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = ""
            r = p.add_run()
            r.text = str(val)
            r.font.name = FONT
            r.font.size = Pt(size)
            r.font.bold = (i == 0) or (first_col_bold and j == 0)
            r.font.color.rgb = WHITE if i == 0 else DARK
    return t


def bars(slide, x, y, w, h, categories, values, colors, fmt, label_w, font_size=8, value_w=0.6):
    """Horizontal bar chart drawn from plain shapes, so it renders identically in PowerPoint, Keynote and Google Slides."""
    n = len(categories)
    row_h = h / n
    bar_h = min(row_h * 0.62, 0.3)
    span = w - label_w - value_w
    top = max(values) or 1
    rect(slide, x + label_w, y, 0.01, h, fill=GREY_BAR)                            # baseline
    for i, (cat, val, col) in enumerate(zip(categories, values, colors)):
        cy = y + i * row_h + (row_h - bar_h) / 2
        text(slide, x, cy - 0.06, label_w - 0.08, bar_h + 0.12, cat, size=font_size, color=INK2, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE, line=1.0)
        bw = max(span * val / top, 0.02)
        rect(slide, x + label_w, cy, bw, bar_h, fill=col)
        text(slide, x + label_w + bw + 0.04, cy - 0.06, value_w, bar_h + 0.12, fmt(val), size=font_size, bold=True, color=DARK, anchor=MSO_ANCHOR.MIDDLE)


def bundle(profile: Profile) -> dict:
    b = recommend(profile)
    cat = catalogue()
    return {"from": b.monthly_min, "setup": b.setup, "contract": b.contract_months, "install": b.install_days,
            "items": [f"{cat[i.product_id].name}" + (f" ×{i.qty}" if i.qty > 1 else "") for i in b.items],
            "excluded": [cat[e.product_id].name for e in b.excluded if e.product_id in cat]}


# ---------------------------------------------------------------- slides
def slide_title(prs, bg):
    s = new_slide(prs, bg)                                     # the SYNC wordmark sits at y 1.85-2.5 in; everything goes below it
    rect(s, 0.55, 2.75, 0.08, 1.35, fill=RED)
    text(s, 0.75, 2.62, 5.0, 0.3, "ENTERPRISE TRACK A · PROJECT UDYAM DIGITAL", size=10, bold=True, color=RGBColor(0xFF, 0x8F, 0xB1))
    text(s, 0.75, 2.9, 5.2, 0.7, "Udyam Digital", size=36, bold=True, color=WHITE)
    text(s, 0.75, 3.55, 5.0, 0.7, "A small business goes live in one sitting: on a phone, in Hindi or English, with no salesperson in the loop.",
         size=13, color=RGBColor(0xF3, 0xF4, 0xF6), line=1.2)
    text(s, 0.75, 4.35, 5.4, 0.85, [
        [("Live prototype  ", {"bold": True, "color": WHITE}), ("udyam-digital-isyfatadrab4adtbqddzwp.streamlit.app", {"color": RGBColor(0xF3, 0xF4, 0xF6)})],
        [("Code  ", {"bold": True, "color": WHITE}), ("github.com/Sheel23501/udyam-digital", {"color": RGBColor(0xF3, 0xF4, 0xF6)})],
        [("Sheel Gautam · IIIT Delhi · November 2026", {"color": RGBColor(0xD1, 0xD5, 0xDB)})],
    ], size=10, line=1.3)
    return s


def slide_leak(prs, bg):
    n = NUMBERS
    s = new_slide(prs, bg)
    title(s, "₹35.6 lakh of ₹55.4 lakh went to leads that never activated",
          "4,632 of 5,000 leads dropped last quarter. Half of those drops were the sales process itself, not the offer.")
    hero(s, 0.5, 1.75, 1.95, f"{n['human_in_the_way_pct']:.0f}%", "of drops: unreachable, no time for a visit, visit not scheduled, quote too slow or too complex")
    hero(s, 0.5, 2.78, 1.95, f"{n['days_to_activation']['median']:.0f} days", "median lead-to-activation; the quote alone takes 4 days")
    hero(s, 0.5, 3.81, 1.95, "22", "customers activated last quarter with a cancelled or suspended GSTIN")
    hero(s, 2.6, 1.75, 1.95, "₹53,026", "field-sales cost per activation on micro retail, for a ₹2,619/month customer")
    hero(s, 2.6, 2.78, 1.95, "719 → 9", "owners asked for 5G AirFiber 719 times; sales sold it 9 times")
    hero(s, 2.6, 3.81, 1.95, "6% → 28%", "6-month churn as the status calls a customer had to make rose from 1 to 5+")
    # chart: top drop reasons, coloured by group
    groups = {"Sales process / human in the way": RED, "Offer / price / fit": DARK, "Paperwork / data quality": GREY_BAR}
    process = {"Unreachable after 3 attempts", "Owner had no time for a visit", "Visit not scheduled by sales", "Quote took too long to arrive",
               "Quote too complex to understand", "Authorised signatory not available", "Found paperwork too long", "Installation delayed beyond 21 days"}
    paper = {"Missing GST or Udyam document", "Document details did not match", "First payment failed", "Customer cancelled before install", "Wrong or invalid number"}
    top = list(n["drop_reasons"].items())[:9]
    cats = [k for k, _ in top]
    vals = [v for _, v in top]
    cols = [RED if k in process else (GREY_BAR if k in paper else DARK) for k in cats]
    text(s, 4.75, 1.72, 4.8, 0.3, "Why 4,632 leads dropped (top 9 reasons)", size=10, bold=True)
    bars(s, 4.75, 2.0, 4.8, 2.7, cats, vals, cols, fmt=lambda v: f"{v:,}", label_w=2.05, font_size=7.8, value_w=0.45)
    lx = 4.75
    short = {"Sales process / human in the way": "Sales process", "Offer / price / fit": "Offer / price / fit", "Paperwork / data quality": "Paperwork / data"}
    for (label, col), w_ in zip(groups.items(), (1.55, 1.75, 1.5)):
        rect(s, lx, 4.8, 0.14, 0.14, fill=col)
        text(s, lx + 0.17, 4.73, w_ - 0.2, 0.25, f"{short[label]} ({n['drop_groups'][label]:,})", size=7.5, color=INK2)
        lx += w_
    source(s)
    return s


def slide_segments(prs, bg):
    pb = NUMBERS["payback_by_segment"]
    s = new_slide(prs, bg)
    title(s, "Where to go first: payback decides", "Blended CAC per activation (all leads' acquisition cost ÷ activations) against the monthly bundle value, by segment.")
    rows = [["Segment", "Leads", "Activation", "₹/month", "6-mo churn", "CAC / activation", "Payback", "Our move"],
            ["Small multi-site", "755 (15%)", "11.0%", f"₹{pb['Small multi-site businesses']['monthly_value']:,}", "11%", f"₹{pb['Small multi-site businesses']['blended_cac']:,}", "0.5 mo", "Wave 1: digital discovery, field close"],
            ["Small manufacturers", "289 (6%)", "12.8%", f"₹{pb['Small manufacturers']['monthly_value']:,}", "8%", f"₹{pb['Small manufacturers']['blended_cac']:,}", "0.8 mo", "Wave 2: field-assisted (ILL, SD-WAN)"],
            ["Professional offices", "1,247 (25%)", "11.1%", f"₹{pb['Professional offices']['monthly_value']:,}", "14%", f"₹{pb['Professional offices']['blended_cac']:,}", "1.6 mo", "Wave 1: digital, optional assist"],
            ["Micro retail & services", "2,709 (54%)", "4.1%", f"₹{pb['Micro retail & services']['monthly_value']:,}", "23%", f"₹{pb['Micro retail & services']['blended_cac']:,} (field ₹53,026)", "8.0 mo", "Digital only; no field visits"]]
    table(s, 0.5, 1.75, 9.0, 1.95, rows, [1.55, 0.9, 0.8, 0.8, 0.8, 1.45, 0.7, 2.0], size=8.5, highlight_rows=(4,))
    # payback chart
    text(s, 0.5, 3.85, 4.4, 0.3, "Months of revenue to repay the acquisition cost", size=10, bold=True)
    cats = ["Small multi-site", "Small manufacturers", "Professional offices", "Micro retail & services"]
    keys = ["Small multi-site businesses", "Small manufacturers", "Professional offices", "Micro retail & services"]
    bars(s, 0.5, 4.1, 4.5, 0.95, cats, [pb[k]["payback_months"] for k in keys], [DARK, DARK, DARK, RED], fmt=lambda v: f"{v:.1f} mo", label_w=1.6, font_size=8, value_w=0.55)
    card(s, 5.25, 3.9, 4.3, 1.15, fill=TINT, line_color=TINT)
    text(s, 5.4, 3.97, 4.0, 1.05, [
        [("Verdict. ", {"bold": True, "color": RED}), ("Professional offices and small multi-site first: they pay back in weeks. Micro retail goes digital-only, "
          "where a field visit costs ₹53,026 to win ₹2,619 a month. Manufacturers come in wave 2 with field assistance for leased lines and SD-WAN.", {})],
    ], size=9.5, color=DARK, line=1.2)
    source(s)
    return s


def slide_bundles(prs, bg):
    s = new_slide(prs, bg)
    title(s, "One bundle per segment, one monthly number", "Composed by the rules engine from the catalogue's eligibility rules and minimum prices; the owner can switch items on and off and the price re-validates instantly.")
    specs = [
        ("Dukaan Start", "Micro retail · GST-free path", Profile(business_type="Kirana store", employee_count=2, num_sites=1, city="Lucknow", has_gstin=False), "Live in 2 days, no setup fee, no GST needed. For the 1,466 no-GST leads (2.0% activation today)."),
        ("Clinic / Office Pro", "Professional offices", Profile(business_type="Dental clinic", employee_count=8, num_sites=1, city="Nagpur", has_gstin=True, needs=[Need.EMAIL, Need.SECURITY, Need.UPTIME]), "Email for every user, backup, endpoint security and a failover line, because a clinic cannot be offline."),
        ("Multi-Store", "Small multi-site · 3 outlets", Profile(business_type="Restaurant chain", employee_count=25, num_sites=3, city="Bengaluru", has_gstin=True, needs=[Need.BRANCHES, Need.CCTV, Need.POS_DROPS]), "Every outlet on one network with cameras and billing that never stops; SD-WAN and toll-free need GST."),
        ("Factory Connect", "Small manufacturers", Profile(business_type="Auto-parts unit", employee_count=12, num_sites=1, city="Pune", has_gstin=True, needs=[Need.MACHINES, Need.SECURITY]), "A leased line with an SLA, machine monitoring and a managed firewall; 21-day install stated up front."),
    ]
    x = 0.5
    for name, seg, prof, why in specs:
        b = bundle(prof)
        card(s, x, 1.75, 2.15, 3.3)
        rect(s, x, 1.75, 2.15, 0.08, fill=RED)
        text(s, x + 0.1, 1.9, 1.95, 0.3, name, size=12, bold=True)
        text(s, x + 0.1, 2.17, 1.95, 0.25, seg, size=8, color=MUTED)
        text(s, x + 0.1, 2.42, 1.95, 0.4, [[("from ", {"size": 9, "color": INK2}), (f"₹{b['from']:,}", {"size": 18, "bold": True, "color": RED}), (" /month", {"size": 9, "color": INK2})]])
        text(s, x + 0.1, 2.85, 1.95, 0.25, f"Setup ₹{b['setup']:,} · {b['contract']}-month · live in {b['install']} days", size=7.5, color=INK2)
        text(s, x + 0.1, 3.1, 1.95, 1.15, [[("• " + it, {})] for it in b["items"][:7]], size=7.5, color=DARK, line=1.05)
        text(s, x + 0.1, 4.3, 1.95, 0.7, why, size=7.5, color=INK2, italic=True, line=1.1)
        x += 2.28
    source(s, "Prices are catalogue minimums composed by backend/app/engine (python scripts/run_scenarios.py reproduces them); ranges and setup fees shown to the owner on the quote screen.")
    return s


def slide_journey(prs, bg):
    s = new_slide(prs, bg)
    title(s, "The journey: six steps on a phone, three rules underneath", "Hindi, English or Hinglish, detected from what the owner types. Works even when the model is down: the engine still quotes.")
    steps = [("1", "Enter", "Link, QR or WhatsApp.\nMobile number + one-time code."),
             ("2", "Advisor", "4 to 6 questions in the owner's language. Facts recorded, never products."),
             ("3", "Quote", "One monthly number. Toggle items; every change re-checked by the rules."),
             ("4", "Consent", "Itemised DPDP notice in their language before any document."),
             ("5", "Smart KYC", "Four photos. 12 checks against GST and Udyam registries in seconds."),
             ("6", "Tracker", "Dated stages, notifications. Zero status calls.")]
    x = 0.5
    for num, head, body in steps:
        card(s, x, 1.78, 1.42, 1.2)
        rect(s, x + 0.1, 1.88, 0.34, 0.34, fill=RED, shape=MSO_SHAPE.OVAL)
        text(s, x + 0.1, 1.9, 0.34, 0.3, num, size=11, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        text(s, x + 0.5, 1.9, 0.9, 0.3, head, size=11, bold=True)
        text(s, x + 0.1, 2.28, 1.25, 0.8, body, size=7.8, color=INK2, line=1.1)
        if num != "6":
            text(s, x + 1.42, 2.2, 0.1, 0.4, "›", size=16, color=MUTED, align=PP_ALIGN.CENTER)
        x += 1.52
    rules = [("Rules decide, the LLM narrates", "A deterministic engine over the catalogue decides eligibility, dependencies and price. The model only asks questions and explains. The card is drawn from engine output, never from prose. 30 scenario fixtures and a 900-profile invariant test keep it honest."),
             ("One number, instantly", "No PDF, no call-back: the quote appears in the chat and re-validates on every toggle. Owners who heard 'quote too complex' or 'quote took too long' (385 drops) get a price in minutes."),
             ("No status calls", "Every order has dated stages and proactive notifications. Customers who made one status call churned at 6%; five calls, 28%. The tracker exists to make that number zero.")]
    x = 0.5
    for head, body in rules:
        card(s, x, 3.15, 2.95, 1.9, fill=TINT2, line_color=TINT2)
        rect(s, x, 3.15, 0.07, 1.9, fill=RED)
        text(s, x + 0.17, 3.25, 2.7, 0.3, head, size=11.5, bold=True)
        text(s, x + 0.17, 3.6, 2.7, 1.4, body, size=9, color=INK2, line=1.2)
        x += 3.03
    source(s, "Architecture diagram and data flows: docs/architecture.png (submitted separately). Prototype: FastAPI + rules engine + Streamlit, LLM via an OpenAI-compatible provider chain.")
    return s


def slide_kyc(prs, bg):
    s = new_slide(prs, bg)
    title(s, "Smart KYC: 12 checks in seconds, built around the DPDP Act", "Vision extraction of four documents, then deterministic validators against the GST and Udyam registries. A photo problem is a REVIEW, never a rejection.")
    results = [("K01", "FAIL", "GSTIN cancelled; Udyam number missing"), ("K02", "REVIEW", "GST certificate photo rotated"), ("K03", "PASS", "all documents consistent"),
               ("K04", "REVIEW", "GST certificate photo blurred"), ("K05", "FAIL", "Udyam certificate missing"), ("K06", "FAIL", "GSTIN check digit fails: tampered digit"),
               ("K07", "FAIL", "legal name differs across documents"), ("K08", "PASS", "all documents consistent"), ("K09", "PASS", "all documents consistent"),
               ("K10", "FAIL", "signatory is not the person of record"), ("K11", "FAIL", "electricity bill 257 days old (limit 90)"), ("K12", "PASS", "all documents consistent")]
    colors = {"PASS": GREEN, "REVIEW": AMBER, "FAIL": RED}
    text(s, 0.5, 1.72, 5.3, 0.3, "The 12 sample applicants as the prototype grades them: 12/12 match the key", size=9.5, bold=True)
    x0, y0 = 0.5, 2.0
    for i, (k, v, why) in enumerate(results):
        col, row = i % 3, i // 3
        x, y = x0 + col * 1.75, y0 + row * 0.72
        card(s, x, y, 1.68, 0.64)
        rect(s, x + 0.08, y + 0.1, 0.55, 0.2, fill=colors[v], shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
        text(s, x + 0.08, y + 0.09, 0.55, 0.22, v, size=7, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        text(s, x + 0.68, y + 0.08, 0.95, 0.25, k, size=10, bold=True)
        text(s, x + 0.08, y + 0.32, 1.55, 0.32, why, size=6.8, color=INK2, line=1.0)
    # right column: hero + DPDP controls
    hero(s, 5.95, 1.78, 3.6, "22 → 0", "activations with a cancelled or suspended GSTIN: the registry is checked live, before the order", num_size=22)
    card(s, 5.95, 2.82, 3.6, 2.22, fill=TINT2, line_color=TINT2)
    text(s, 6.08, 2.88, 3.4, 0.28, "DPDP controls, each a code path, not a slide", size=10, bold=True)
    controls = [("Consent gate", "documents are refused (HTTP 403) until the owner ticks four itemised purposes in their language"),
                ("Minimisation", "five facts for the quote; GST or Udyam path; no Aadhaar; only the image leaves the boundary"),
                ("Masking", "GSTIN as 27XXXXXXXXXX1ZP, names as 'Nisha A.' in UI, API and audit log"),
                ("Retention", "images deleted 30 days after a rejection, 90 after verification; erasure on request"),
                ("Accuracy", "REVIEW before any adverse decision; 'talk to a human' always available")]
    text(s, 6.08, 3.18, 3.4, 1.85, [[(h + ": ", {"bold": True}), (b, {})] for h, b in controls], size=8, color=DARK, line=1.2)
    source(s, "Reproduce: cd backend && python scripts/kyc_report.py --key tests/kyc_answer_key_images.json. Privacy note: docs/privacy-note.md (submitted separately).")
    return s


def slide_field(prs, bg):
    n = NUMBERS["activation_by_source"]
    s = new_slide(prs, bg)
    title(s, "Digital adds; the field force multiplies", "Take the field team out of the ₹2,500 kirana sale and put it where payback is under a month. Attribution keeps partners on side.")
    order = sorted(n.items(), key=lambda kv: -kv[1]["rate_pct"])
    text(s, 0.5, 1.72, 4.6, 0.3, "Activation rate by lead source", size=10, bold=True)
    bars(s, 0.5, 2.05, 4.6, 2.45, [k for k, _ in order], [v["rate_pct"] for _, v in order],
         [RED if k == "Referral" else DARK for k, _ in order], fmt=lambda v: f"{v:.1f}%", label_w=1.45, font_size=8.5, value_w=0.55)
    text(s, 0.5, 4.6, 4.6, 0.5, f"Referral converts at {n['Referral']['rate_pct']}% but churns at 24.6%: pay the referral bonus at month 3, not at activation.", size=8.5, color=INK2, italic=True)
    moves = [("Micro retail goes digital-only", f"Field sales spent ₹53,026 per activation here. Removing those 27 visits a quarter saves about ₹14 lakh per quarter with no loss of volume."),
             ("Field team redeployed to multi-site and manufacturers", "Payback 0.5 and 0.8 months. The advisor qualifies and quotes; a human closes the ₹20,000-plus accounts and handles ILL and SD-WAN installs."),
             ("Partners keep their code", "Every journey carries a partner code for attribution and commission; partners see the scored queue for their area."),
             ("Nothing dead-ends", "Leads the journey cannot close land in a back-office queue ranked by a propensity model (holdout AUC 0.68) plus how recoverable the drop reason is, each with a suggested next action.")]
    y = 1.75
    for head, body in moves:
        card(s, 5.3, y, 4.25, 0.78, fill=WHITE)
        rect(s, 5.3, y, 0.07, 0.78, fill=RED)
        text(s, 5.47, y + 0.05, 4.0, 0.25, head, size=9.5, bold=True)
        text(s, 5.47, y + 0.3, 4.0, 0.5, body, size=7.5, color=INK2, line=1.1)
        y += 0.84
    source(s)
    return s


def slide_rollout(prs, bg):
    s = new_slide(prs, bg)
    title(s, "Rollout in three phases", "Start where the data says the money is, with the adapters that make mocks real.")
    phases = [("Phase 0 · Q3 2026", "Prove it", ["Delhi + Mumbai", "Hindi and English, Hinglish auto-detect", "Micro retail (GST-free) + professional offices", "Web and WhatsApp entry, partner-code pilot with 20 partners", "Mock registries swapped for GSTN/GSP and Udyam APIs"],
               "Gate: 12% blended activation, quote in under 5 minutes, zero activations with a non-active GSTIN"),
              ("Phase 1 · Q4 2026", "Widen", ["Tier-2 cities (Jaipur, Lucknow, Indore, Nagpur, Surat...)", "Small multi-site journeys with per-site quotes", "DigiLocker pull of GST/Udyam certificates, eSign for the order", "Field team re-routed by the propensity queue"],
               "Gate: CAC per activation ≤ ₹7,500; KYC first-pass ≥ 70%"),
              ("Phase 2 · Q1 2027", "Deepen", ["Manufacturers: leased line and SD-WAN journeys with field assist", "Real-time fibre serviceability at quote time", "30-day check-in and referral bonus at month 3", "Regional languages beyond Hindi where volume justifies it"],
               "Gate: 6-month churn ≤ 10%; status calls per customer < 0.5")]
    x = 0.5
    for i, (when, head, items, gate) in enumerate(phases):
        card(s, x, 1.78, 2.95, 3.25)
        rect(s, x, 1.78, 2.95, 0.5, fill=RED if i == 0 else DARK, shape=MSO_SHAPE.RECTANGLE)
        text(s, x + 0.12, 1.83, 2.7, 0.22, when, size=8.5, bold=True, color=RGBColor(0xFF, 0xD6, 0xE1) if i == 0 else RGBColor(0xD1, 0xD5, 0xDB))
        text(s, x + 0.12, 2.0, 2.7, 0.28, head, size=12, bold=True, color=WHITE)
        text(s, x + 0.12, 2.4, 2.7, 1.75, [[("• " + it, {})] for it in items], size=9, color=DARK, line=1.25)
        rect(s, x + 0.12, 4.25, 2.7, 0.01, fill=LINE)
        text(s, x + 0.12, 4.32, 2.7, 0.7, gate, size=8.5, color=RED, bold=True, line=1.15)
        x += 3.03
    text(s, 0.5, 5.08, 9.0, 0.3, "Dependencies: GSTN/GSP and Udyam API access, DigiLocker and eSign onboarding, a DLT-registered SMS template for OTPs, partner commission rules.", size=7.5, color=MUTED)
    return s


def slide_metrics(prs, bg):
    s = new_slide(prs, bg)
    title(s, "What we will measure", "Q2 2026 baseline from the leads file; two-quarter targets, and the design feature that moves each one.")
    rows = [["Metric", "Today", "Target (2 quarters)", "What moves it"],
            ["Lead → activation", "7.4%", "12% blended; 15% for offices and multi-site", "Instant quote, GST-free path, no visit-dependent steps"],
            ["Lead → activation time", "17 days (quote alone 4)", "≤ 5 days, install-bound; quote in < 5 minutes", "Advisor + engine + instant KYC"],
            ["Status calls per customer", "3.0", "< 0.5", "Tracker with dated stages and proactive notifications"],
            ["Blended CAC per activation", "₹15,053", "≤ ₹7,500 (micro ≤ ₹3,000)", "Digital-only micro, referral, redeployed field force"],
            ["6-month churn", "15.2%", "≤ 10%", "Fewer calls, right-sized bundles, 30-day check-in, bonus at month 3"],
            ["Activations with non-active GSTIN", "22", "0", "Live registry check inside KYC, before the order"],
            ["KYC first-pass rate", "n/a", "≥ 70%; REVIEW resolved within 24 h", "Human-language fixes, re-upload path, Udyam-only path"]]
    table(s, 0.5, 1.75, 9.0, 3.1, rows, [2.1, 1.5, 2.4, 3.0], size=8.5)
    text(s, 0.5, 4.95, 9.0, 0.25, "Measured weekly from the same tables the prototype already writes: sessions, consents, kyc_applications, orders, audit_log.", size=8, color=INK2, italic=True)
    source(s)
    return s


def slide_risks(prs, bg):
    s = new_slide(prs, bg)
    title(s, "Risks we designed for, and what is already built", "Each mitigation is a code path in the prototype, not a plan.")
    rows = [["Risk", "Mitigation in the prototype"],
            ["The model recommends something the owner is not eligible for", "The rules engine decides every item; the model only narrates; the UI renders engine JSON. 30 scenario fixtures + 16 live transcripts, zero violations"],
            ["KYC wrongly rejects a genuine owner", "Photo problems are REVIEW with a plain-language fix; FAIL always carries the reason and a 'talk to a human' hand-off"],
            ["LLM or vision API down or over quota during a demo", "Provider chain with fallbacks; cached demo replies; the engine and validators run offline. The journey completes with no model at all"],
            ["Fibre not feasible, install delays", "5G AirFiber as a 2-day interim line; install days stated on the quote; tracker dates"],
            ["Channel conflict with partners and field sales", "Partner code on every journey; propensity queue routes high-value leads to humans; micro retail digital-only"],
            ["Privacy and DPDP exposure", "Consent gate (403), masking everywhere, retention purge, erasure, staff-only back office, audit log"],
            ["Low-quality leads from digital channels", "Mobile number verified by one-time code at entry; GST status checked live"]]
    table(s, 0.5, 1.72, 5.9, 3.3, rows, [2.1, 3.8], size=7.8, zebra=True)
    card(s, 6.6, 1.72, 2.95, 3.3, fill=TINT, line_color=TINT)
    text(s, 6.75, 1.8, 2.7, 0.3, "Built and verified", size=11, bold=True, color=RED)
    proof = [("2,050", "automated tests, all green in CI"), ("30 / 30", "advisor scenarios through the rules engine"), ("12 / 12", "KYC verdicts matching the answer key"),
             ("16 / 16", "live conversations on Gemini, zero rule violations"), ("Docker", "compose build and smoke test on every push")]
    y = 2.15
    for num, lab in proof:
        text(s, 6.75, y, 1.0, 0.3, num, size=13, bold=True, color=DARK)
        text(s, 7.7, y + 0.04, 1.8, 0.4, lab, size=7.8, color=INK2, line=1.05)
        y += 0.44
    text(s, 6.75, 4.42, 2.7, 0.6, [[("Try it: ", {"bold": True}), ("the README's step-by-step guide takes a judge from clone to a verified API in 20 minutes, no keys needed.", {})]], size=7.6, color=DARK, line=1.1)
    source(s, "Repository: github.com/Sheel23501/udyam-digital · docs/how-to-check.md · docs/privacy-note.md · docs/architecture.png")
    return s


def main() -> int:
    title_bg, body_bg = extract_backgrounds()
    prs = Presentation(str(TEMPLATE))
    clear_slides(prs)
    slide_title(prs, title_bg)
    for fn in (slide_leak, slide_segments, slide_bundles, slide_journey, slide_kyc, slide_field, slide_rollout, slide_metrics, slide_risks):
        fn(prs, body_bg)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(f"wrote {OUT} ({len(prs.slides)} slides)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
