"""Deterministic narration of an engine Bundle in English or Hindi.

Used (a) as the advisor's reply when every LLM provider is down, so the demo never dead-ends, and (b) by the UI
card and the scenario runner. Every sentence is generated from engine output, never guessed."""
from ..engine.catalogue import catalogue
from ..engine.models import Bundle, Exclusion, Note, Reason

UNIT_WORD = {
    "en": {"site": "site", "line": "line", "ip": "IP", "channel": "channel", "number": "number", "pack": "pack",
           "account": "account", "user": "user", "counter": "counter", "device": "device", "camera": "camera", "vehicle": "vehicle"},
    "hi": {"site": "लोकेशन", "line": "लाइन", "ip": "IP", "channel": "चैनल", "number": "नंबर", "pack": "पैक",
           "account": "अकाउंट", "user": "यूज़र", "counter": "काउंटर", "device": "डिवाइस", "camera": "कैमरा", "vehicle": "गाड़ी"},
}


def _unit(unit: str, lang: str) -> str:
    key = unit.lower().replace("per ", "").strip()
    return UNIT_WORD.get(lang, UNIT_WORD["en"]).get(key, key)


def reason_sentence(ex: Exclusion, lang: str) -> str:
    cat = catalogue()
    p = cat.get(ex.product_id)
    name = p.name if p else ex.product_id
    if lang == "hi":
        if ex.reason == Reason.TIER_NOT_AVAILABLE:
            return f"{name} अभी केवल बड़े (टियर-1) शहरों में उपलब्ध है, इसलिए शामिल नहीं किया।"
        if ex.reason == Reason.MIN_EMPLOYEES:
            return f"{name} के लिए कम से कम {p.min_employees} कर्मचारी चाहिए, इसलिए शामिल नहीं किया।"
        if ex.reason == Reason.MIN_SITES:
            return f"{name} के लिए कम से कम {p.min_sites} लोकेशन चाहिए, इसलिए शामिल नहीं किया।"
        if ex.reason == Reason.GSTIN_REQUIRED:
            return f"{name} के लिए सक्रिय GST पंजीकरण ज़रूरी है; GST बनवाने में हम मदद कर सकते हैं।"
        if ex.reason == Reason.GSTIN_NOT_ACTIVE:
            return f"{name} के लिए सक्रिय GST चाहिए; दिया गया GSTIN सक्रिय नहीं है।"
        if ex.reason == Reason.NEEDS_BASE_LINE:
            return f"{name} Accel की इंटरनेट लाइन पर ही चलता है; लाइन जोड़ने पर इसे शामिल किया जा सकता है।"
        if ex.reason == Reason.UNKNOWN_PRODUCT:
            return f"{ex.product_id} हमारी सूची में नहीं है।"
        return ex.detail
    if ex.reason == Reason.GSTIN_REQUIRED:
        return f"{name} needs an active GST registration, so I left it out; we can help you register."
    if ex.reason == Reason.NEEDS_BASE_LINE:
        return f"{name} runs only on an Accel internet line; add a line and it can be included."
    return ex.detail + (", so I left it out." if ex.reason in (Reason.TIER_NOT_AVAILABLE, Reason.MIN_EMPLOYEES, Reason.MIN_SITES) else ".")


def note_sentence(note: Note, lang: str) -> str:
    cat = catalogue()
    base = cat[note.product_id].name if note.product_id in cat else note.product_id
    dep = cat[note.because_of].name if note.because_of in cat else note.because_of
    if lang == "hi":
        if note.type == "auto_added":
            return f"{base} जोड़ा गया क्योंकि {dep} को इसकी ज़रूरत है।"
        if note.type == "replaced":
            return f"{dep} के लिए फाइबर लाइन चाहिए, इसलिए AirFiber की जगह {base} रखा गया।"
        if note.type == "fallback":
            return f"{dep} की जगह {base} दिया गया।"
        return note.detail
    if note.type == "auto_added":
        return f"I added {base} because {dep} needs it."
    if note.type == "replaced":
        return f"{dep} needs a fibre line, so I upgraded AirFiber to {base}."
    if note.type == "fallback":
        return f"I offered {base} instead of {dep}."
    return note.detail


def explain(b: Bundle, lang: str = "en") -> str:
    """Plain-language summary of a Bundle. Hindi for 'hi', English for everything else (Hinglish readers read English)."""
    lang = "hi" if lang == "hi" else "en"
    cat = catalogue()
    lines: list[str] = []
    if not b.items:                                           # everything asked for was excluded: say so, no ₹0 quote
        lines.append("अभी कुछ शामिल नहीं हो सका:" if lang == "hi" else "I could not include anything yet:")
        lines += [f"• {reason_sentence(ex, lang)}" for ex in b.excluded]
        return "\n".join(lines)
    lines.append("आपके बिज़नेस के लिए मेरा सुझाव:" if lang == "hi" else "Here is what I suggest for your business:")
    for it in b.items:
        p = cat[it.product_id]
        unit = _unit(p.unit, lang)
        if lang == "en" and it.qty > 1 and unit.islower():
            unit += "s"
        qty = f" × {it.qty} {unit}" if it.qty > 1 else ""
        lines.append(f"• {p.name}{qty} — {p.description}")
    if lang == "hi":
        lines.append(f"कुल ₹{b.monthly_min:,} प्रति माह से शुरू (विकल्पों के अनुसार ₹{b.monthly_max:,} तक)। "
                     f"एक बार का सेटअप ₹{b.setup:,}, {b.contract_months} महीने का अनुबंध, लगभग {b.install_days} दिन में चालू।")
    else:
        lines.append(f"From ₹{b.monthly_min:,} per month (up to ₹{b.monthly_max:,} depending on options). "
                     f"One-time setup ₹{b.setup:,}, {b.contract_months}-month contract, live in about {b.install_days} days.")
    if b.excluded:
        lines.append("शामिल नहीं किया:" if lang == "hi" else "Not included:")
        lines += [f"• {reason_sentence(ex, lang)}" for ex in b.excluded]
    if b.notes:
        lines += [f"ℹ️ {note_sentence(n, lang)}" for n in b.notes]
    return "\n".join(lines)
