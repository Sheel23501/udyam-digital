#!/usr/bin/env python
"""Build the 7-slide submission on the Airtel SYNC submission template.

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
OUT = ROOT / "docs" / "UdyamDigital_IIITDelhi.pptx"      # TeamName_CampusName, as the submission rules ask
NUMBERS = json.loads((ROOT / "docs" / "charts" / "numbers.json").read_text(encoding="utf-8"))
WORK = ROOT / "docs" / ".deck_assets"

RED, DARK, INK2, MUTED, LINE = RGBColor(0xE4, 0x00, 0x46), RGBColor(0x1A, 0x1A, 0x1A), RGBColor(0x4B, 0x55, 0x63), RGBColor(0x8A, 0x8F, 0x98), RGBColor(0xE5, 0xE7, 0xEB)
TINT, TINT2, WHITE, GREEN, AMBER = RGBColor(0xFD, 0xE7, 0xEE), RGBColor(0xF6, 0xF6, 0xF8), RGBColor(0xFF, 0xFF, 0xFF), RGBColor(0x0C, 0xA3, 0x0C), RGBColor(0xE0, 0x8A, 0x00)
GREY_BAR = RGBColor(0xB8, 0xBC, 0xC4)
FONT = "Arial"
W, H = Inches(10), Inches(5.625)
SOURCE = f"Source: smb_leads.csv, {NUMBERS['leads']:,} leads ({NUMBERS['period'][0]} to {NUMBERS['period'][1]}); every figure reproduced by backend/scripts/make_charts.py."


# ---------------------------------------------------------------- helpers
def erase(im, box, ref_top, ref_bottom):
    """Paint a box out by blending, column by column, the rows just above and just below it."""
    from PIL import ImageFilter
    x0, y0, x1, y1 = box
    px = im.load()
    for x in range(x0, x1):
        top = [px[x, y] for y in range(ref_top - 2, ref_top + 1)]
        bot = [px[x, y] for y in range(ref_bottom, ref_bottom + 3)]
        t = tuple(sum(c[i] for c in top) // len(top) for i in range(3))
        b = tuple(sum(c[i] for c in bot) // len(bot) for i in range(3))
        for y in range(y0, y1):
            f = (y - y0) / max(y1 - y0 - 1, 1)
            px[x, y] = tuple(round(t[i] * (1 - f) + b[i] * f) for i in range(3))
    soft = im.crop((x0 - 6, y0 - 6, x1 + 6, y1 + 6)).filter(ImageFilter.GaussianBlur(2))
    im.paste(soft.crop((6, 6, 6 + x1 - x0, 6 + y1 - y0)), (x0, y0))


def extract_backgrounds() -> tuple[Path, Path]:
    from PIL import Image
    WORK.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(TEMPLATE)
    title_bg, body_bg = WORK / "title_bg.jpg", WORK / "body_bg.jpg"
    for src, dst, box, rt, rb in (("ppt/media/image2.jpg", title_bg, (1490, 998, 1900, 1046), 1050, 1050),   # slide 1 of the template
                                  ("ppt/media/image1.jpg", body_bg, (1585, 1000, 1915, 1062), 996, 1064)):  # slide 2 of the template
        dst.write_bytes(z.read(src))
        im = Image.open(dst).convert("RGB")
        erase(im, box, rt, rb)                                  # removes the "Platform Partner unstop" mark
        if dst == title_bg:
            erase(im, (1745, 984, 1808, 1000), 1050, 1050)      # top edge of the logo circle
        im.save(dst, quality=95)
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
LIVE_URL = "https://udyam-digital-isyfatadrab4adtbqddzwp.streamlit.app"
REPO_URL = "https://github.com/Sheel23501/udyam-digital"


def link_button(slide, x, y, w, label, shown, url, fill, outline=None):
    """A pill that opens `url` on click (the whole shape and the text are both links)."""
    sh = rect(slide, x, y, w, 0.38, fill=fill, line_color=outline, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5, line_w=1.5)
    sh.click_action.hyperlink.address = url
    tf = sh.text_frame
    tf.margin_left = Inches(0.18)
    tf.margin_right = Inches(0.1)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.word_wrap = False
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    for seg, bold, size in ((label + "   ", True, 8.5), (shown, True, 11)):
        r = p.add_run()
        r.text = seg
        r.font.name = FONT
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = WHITE
        if seg == shown:
            r.hyperlink.address = url
    return sh


def slide_title(prs, bg):
    s = new_slide(prs, bg)                                     # the SYNC wordmark sits at y 1.85-2.5 in; everything goes below it
    rect(s, 0.55, 2.75, 0.08, 1.35, fill=RED)
    text(s, 0.75, 2.62, 5.0, 0.3, "ENTERPRISE TRACK A · PROJECT UDYAM DIGITAL", size=10, bold=True, color=RGBColor(0xFF, 0x8F, 0xB1))
    text(s, 0.75, 2.9, 5.2, 0.7, "Udyam Digital", size=36, bold=True, color=WHITE)
    text(s, 0.75, 3.55, 5.0, 0.7, "A small business goes live in one sitting: on a phone, in Hindi or English, with no salesperson in the loop.",
         size=13, color=RGBColor(0xF3, 0xF4, 0xF6), line=1.2)
    text(s, 0.75, 4.12, 5.6, 0.3, [[("Sheel Gautam · Vikas Meena", {"bold": True, "color": WHITE, "size": 12}),
                                    ("   IIIT Delhi · November 2026", {"color": RGBColor(0xD1, 0xD5, 0xDB), "size": 10})]])
    link_button(s, 0.75, 4.55, 5.55, "LIVE PROTOTYPE", "udyam-digital-isyfatadrab4adtbqddzwp.streamlit.app", LIVE_URL, RED)
    link_button(s, 0.75, 5.0, 5.55, "CODE ON GITHUB", "github.com/Sheel23501/udyam-digital", REPO_URL, RGBColor(0x1A, 0x1A, 0x1A), outline=WHITE)
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


def architecture_crop() -> Path:
    """The slide has its own title, so drop the title band of the diagram and keep the boxes at full resolution."""
    from PIL import Image
    im = Image.open(ROOT / "docs" / "architecture.png").convert("RGB")
    out = WORK / "architecture_crop.png"
    im.crop((0, int(im.height * 0.115), im.width, im.height)).save(out)
    return out


def slide_architecture(prs, bg):
    s = new_slide(prs, bg)
    title(s, "Our approach: rules decide, the LLM narrates")
    # left: the six steps the owner sees
    steps = [("Enter", "link, QR or WhatsApp; mobile + one-time code"), ("Advisor", "4 to 6 questions in Hindi or English"), ("Quote", "one monthly number, re-checked on every toggle"),
             ("Consent", "itemised DPDP notice before any document"), ("Smart KYC", "four photos, 12 checks in seconds"), ("Tracker", "dated stages, zero status calls")]
    y = 1.5
    for i, (head, body) in enumerate(steps, 1):
        rect(s, 0.5, y + 0.02, 0.24, 0.24, fill=RED, shape=MSO_SHAPE.OVAL)
        text(s, 0.5, y + 0.03, 0.24, 0.22, str(i), size=8, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        text(s, 0.8, y - 0.02, 1.5, 0.6, [[(head, {"bold": True, "size": 9.5})], [(body, {"size": 7.6, "color": INK2})]], line=1.0)
        y += 0.6
    # right: the diagram at full size
    img = architecture_crop()
    from PIL import Image
    w_px, h_px = Image.open(img).size
    h_in = 3.58
    w_in = h_in * w_px / h_px
    x0 = 9.6 - w_in
    card(s, x0 - 0.04, 1.43, w_in + 0.08, h_in + 0.06, fill=RGBColor(0xFC, 0xFC, 0xFA), line_color=LINE)
    s.shapes.add_picture(str(img), Inches(x0), Inches(1.46), Inches(w_in), Inches(h_in))
    source(s, "Consent gates every document; the engine still quotes if the model is down. Full-resolution diagram: docs/architecture.png (submitted separately).")
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


def slide_competitive(prs, bg):
    s = new_slide(prs, bg)
    title(s, "Competitive analysis: where Udyam Digital differs",
          "Public sources only, reviewed November 2026. \"Not public\" means we found no published detail, not that the feature is absent.")
    NP = "Not public"
    rows = [["", "Airtel today", "Jio Business", "Vi Business", "Tata Tele (TTBS)", "Udyam Digital"],
            ["How an owner starts", "Field visit or call-back. 48.5% of drops are the sales process", "Plan page, then business details and KYC documents online (third-party summary)",
             "Online form, then a rep calls back within 48 h (corporate postpaid)", "Sales-led. No public self-serve flow found", "Self-serve on the owner's phone, in Hindi or English"],
            ["Price", "Quote after a visit. The quote alone takes 4 days", "Tiered plans, reported from ₹501 at the 2021 launch", "Postpaid from ₹299 a line",
             "Pay-as-you-grow. Prices not public", "One monthly number in the chat, re-checked on every toggle"],
            ["What is bundled", "25 products, sold one by one", "Connectivity plus apps: Jio Online, Teams and Meet licences (2021)", "Mobile plans, data pooling for small firms",
             "Connectivity, cloud calling and security suites", "A rules-checked bundle per segment with dependencies closed"],
            ["KYC", "Paper at the visit. 22 activations had a non-active GSTIN", "GSTIN or PAN documents (third-party summary)", "Assisted KYC at the doorstep. A DoT notice reported on business lines without end-user KYC",
             NP, "12 checks in seconds against GST and Udyam, after consent"],
            ["Language and tracking", "Status by phone: 3.0 calls per customer", NP, NP, NP, "Hindi and English. Dated tracker, zero status calls"]]
    t = table(s, 0.5, 1.75, 9.0, 3.05, rows, [1.05, 1.6, 1.65, 1.65, 1.45, 1.6], size=7, first_col_bold=True)
    for i in range(len(rows)):
        c = t.cell(i, 5)
        c.fill.solid()
        c.fill.fore_color.rgb = RED if i == 0 else TINT
        if i:
            for p_ in c.text_frame.paragraphs:
                for r_ in p_.runs:
                    r_.font.bold = True
    for i in range(1, len(rows)):
        for j in (2, 3, 4):
            if rows[i][j] == NP:
                for p_ in t.cell(i, j).text_frame.paragraphs:
                    for r_ in p_.runs:
                        r_.font.color.rgb = MUTED
                        r_.font.italic = True
    text(s, 0.5, 4.85, 9.0, 0.3, "None of the public material we reviewed shows one phone journey from quote to registry-checked KYC to a validated bundle.",
         size=8.5, bold=True, color=RED, line=1.05)
    source(s, "Sources: businesstoday.in (Jio, Mar 2021), myvi.in corporate postpaid pages, bharatnet.in (DoT notice), tatatelebusiness.com and tele.net.in. Airtel and Udyam Digital columns: smb_leads.csv and the prototype.")
    return s


BUNDLE_PROFILES = [
    ("Small multi-site", "Multi-Store", Profile(business_type="Restaurant chain", employee_count=25, num_sites=3, city="Bengaluru", has_gstin=True, needs=[Need.BRANCHES, Need.CCTV, Need.POS_DROPS])),
    ("Small manufacturers", "Factory Connect", Profile(business_type="Auto-parts unit", employee_count=12, num_sites=1, city="Pune", has_gstin=True, needs=[Need.MACHINES, Need.SECURITY])),
    ("Professional offices", "Clinic / Office Pro", Profile(business_type="Dental clinic", employee_count=8, num_sites=1, city="Nagpur", has_gstin=True, needs=[Need.EMAIL, Need.SECURITY, Need.UPTIME])),
    ("Micro retail & services", "Dukaan Start", Profile(business_type="Kirana store", employee_count=2, num_sites=1, city="Lucknow", has_gstin=False)),
]


def slide_impact(prs, bg):
    pb = NUMBERS["payback_by_segment"]
    n_act = NUMBERS["activated"]
    keys = ["Small multi-site businesses", "Small manufacturers", "Professional offices", "Micro retail & services"]
    blended_cac = round(sum(pb[k]["blended_cac"] * pb[k]["activations"] for k in keys) / n_act)
    avg_value = sum(pb[k]["monthly_value"] * pb[k]["activations"] for k in keys) / n_act
    spend_lakh = blended_cac * n_act / 1e5
    target_acts = round(NUMBERS["leads"] * 0.12)
    extra = target_acts - n_act
    extra_mrr_lakh = extra * avg_value / 1e5
    s = new_slide(prs, bg)
    title(s, "Impact: 12% activation at half the cost per customer",
          "Two-quarter targets on the same lead volume and acquisition spend, measured weekly from tables the prototype already writes.")
    kpis = [("Lead to activation", "7.4% → 12%"), ("Cost per activation", f"₹{blended_cac:,} → ≤₹7,500"), ("Lead to live", "17 days → ≤5 days"),
            ("Status calls per customer", "3.0 → under 0.5"), ("6-month churn", "15.2% → ≤10%"), ("Non-active GSTIN activations", "22 → 0")]
    for i, (lab, val) in enumerate(kpis):
        x, y = 0.5 + (i % 2) * 2.3, 1.75 + (i // 2) * 1.08
        card(s, x, y, 2.2, 0.98)
        text(s, x + 0.1, y + 0.08, 2.0, 0.25, lab, size=8.5, color=INK2)
        text(s, x + 0.1, y + 0.36, 2.0, 0.5, val, size=15, bold=True, color=RED, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 5.2, 1.72, 4.3, 0.3, "Who we win first, and what they buy", size=10, bold=True)
    rows = [["Segment", "Bundle, from ₹/month", "Payback"]]
    for (seg, name, prof), k in zip(BUNDLE_PROFILES, keys):
        b = bundle(prof)
        pay = f"{pb[k]['payback_months']:.1f} mo" if seg != "Micro retail & services" else "8.0 → 1.2 mo"
        rows.append([seg, f"{name} ₹{b['from']:,}", pay])
    table(s, 5.2, 2.0, 4.35, 1.5, rows, [1.45, 1.85, 1.05], size=8, highlight_rows=(4,))
    text(s, 5.2, 3.52, 4.35, 0.3, "Micro retail goes digital-only: at a ₹3,000 cost per activation its payback falls from 8.0 to about 1.2 months.", size=7.5, color=INK2, italic=True, line=1.05)
    card(s, 5.2, 3.95, 4.35, 1.1, fill=TINT, line_color=TINT)
    text(s, 5.32, 4.0, 4.1, 1.02, [[("What it is worth. ", {"bold": True, "color": RED}),
         (f"The same ₹{spend_lakh:.1f} lakh at 12% activation brings {target_acts} customers a quarter instead of {n_act}, {extra} more. "
          f"At today's segment mix and ₹{avg_value:,.0f} average monthly value, that is about ₹{extra_mrr_lakh:.1f} lakh more monthly recurring revenue, before churn.", {})]],
         size=8.5, color=DARK, line=1.15)
    source(s, "Projection from the Apr to Jun 2026 leads file; it assumes the extra customers match today's segment mix. Targets are ours, not Airtel commitments.")
    return s


def slide_rollout_risks(prs, bg):
    s = new_slide(prs, bg)
    title(s, "Rollout, risks and proof", "Start where the data says the money is, and say plainly what could go wrong.")
    phases = [("Q3 2026", "Prove it", "Delhi and Mumbai, Hindi and English. Micro retail and professional offices. Live GSTN and Udyam APIs. Partner-code pilot.", "Gate: 12% activation, quote in under 5 minutes"),
              ("Q4 2026", "Widen", "Tier-2 cities. Multi-site journeys. DigiLocker and eSign. Field team routed by the propensity queue.", "Gate: cost per activation ≤ ₹7,500, KYC first pass ≥ 70%"),
              ("Q1 2027", "Deepen", "Manufacturers with field assist for leased line and SD-WAN. Serviceability at quote time. Regional languages.", "Gate: 6-month churn ≤ 10%, status calls under 0.5")]
    y = 1.72
    for i, (when, head, body, gate) in enumerate(phases):
        card(s, 0.5, y, 4.45, 0.86)
        rect(s, 0.5, y, 0.95, 0.86, fill=RED if i == 0 else DARK)
        text(s, 0.52, y + 0.12, 0.91, 0.25, when, size=8, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        text(s, 0.52, y + 0.38, 0.91, 0.3, head, size=11, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        text(s, 1.52, y + 0.04, 3.38, 0.55, body, size=7.6, color=DARK, line=1.08)
        text(s, 1.52, y + 0.6, 3.38, 0.25, gate, size=7.3, bold=True, color=RED)
        y += 0.93
    rows = [["Risk", "What we built against it"],
            ["The model suggests something the owner cannot have", "The rules engine decides every item. 30 scenarios and 16 live chats, zero violations"],
            ["KYC wrongly rejects a genuine owner", "Photo problems become REVIEW with a plain fix. Every FAIL has a reason and a human hand-off"],
            ["Telecom end-user KYC still applies to SIMs", "Registry checks are added to the DoT-required step, not a replacement. A reported DoT notice to Vi shows the exposure"],
            ["Model or API down mid-journey", "Provider chain, cached replies, offline engine. The journey completes with no model"],
            ["Channel conflict with partners and field sales", "Partner code on every journey. High-value leads routed to humans"],
            ["DPDP exposure", "Consent gate, masking, retention purge, erasure, audit log"]]
    table(s, 5.1, 1.72, 4.45, 2.72, rows, [1.5, 2.95], size=7, zebra=True)
    proof = [("2,050", "automated tests green in CI"), ("30 / 30", "advisor scenarios pass"), ("12 / 12", "KYC verdicts match the key"), ("16 / 16", "live chats, zero violations")]
    x = 0.5
    for num, lab in proof:
        card(s, x, 4.55, 2.15, 0.5, fill=TINT, line_color=TINT)
        text(s, x + 0.08, 4.6, 0.85, 0.4, num, size=12, bold=True, color=RED, anchor=MSO_ANCHOR.MIDDLE)
        text(s, x + 0.9, 4.6, 1.22, 0.4, lab, size=7.2, color=INK2, anchor=MSO_ANCHOR.MIDDLE, line=1.0)
        x += 2.28
    source(s, "Live prototype and code are linked on the title slide. Step-by-step checks: docs/how-to-check.md. Privacy note and architecture diagram are submitted separately.")
    return s


def main() -> int:
    title_bg, body_bg = extract_backgrounds()
    prs = Presentation(str(TEMPLATE))
    clear_slides(prs)
    import re
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    theme = prs.slide_layouts[10].slide_master.part.part_related_by(RT.THEME)
    xml = theme.blob.decode("utf-8")
    xml = re.sub(r'(<a:(?:hlink|folHlink)>\s*<a:srgbClr val=")[0-9A-Fa-f]{6}', r'\1FFFFFF', xml)
    theme._blob = xml.encode("utf-8")
    slide_title(prs, title_bg)
    for fn in (slide_leak, slide_architecture, slide_kyc, slide_competitive, slide_impact, slide_rollout_risks):
        fn(prs, body_bg)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(f"wrote {OUT} ({len(prs.slides)} slides)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
