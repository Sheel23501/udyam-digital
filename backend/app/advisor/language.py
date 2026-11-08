"""Language and number helpers for the advisor: script detection, Hinglish detection, Hindi number words, city names.

These are deterministic safety nets. The model is also told the same conventions in the system prompt, but a
tool argument like employee_count="paanch" or city="Bombay" must still land correctly."""
import re

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
# Bengali, Gurmukhi, Gujarati, Oriya, Tamil, Telugu, Kannada, Malayalam blocks
OTHER_INDIC = re.compile(r"[ঀ-ൿ]")
LATIN_WORD = re.compile(r"[A-Za-z]+")

# Unambiguous Roman-script Hindi words (English look-alikes such as "do", "log", "band" are deliberately left out).
HINGLISH_MARKERS = frozenset("""
hai hain kya nahi nahin chahiye chaiye mujhe hamare humare humko hamein hume kitna kitne kaise dukaan dukan karna karte
karta bataiye batao hota hoti mera meri mere wala wali wale bhi abhi sirf bahut bohot zyada paise rupaye rupay mahina
mahine kaam chalta chalti theek thik accha acha haan matlab lekin aur paanch panch teen chaar saat aath nau dus mein
apna apni yeh woh toh karo karein hoga hogi chahta chahti kuch jaldi lagta lagti dikhao bhejo liye saath baar jaata
jaati jata jati rehta rehti milta milti deta deti lena dena bata sakte sakta sakti kar
""".split())

NUMBER_WORDS = {
    "ek": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "pach": 5,
    "chhe": 6, "che": 6, "cheh": 6, "chah": 6, "chhah": 6, "saat": 7, "sat": 7, "aath": 8, "ath": 8, "nau": 9,
    "das": 10, "dus": 10, "gyarah": 11, "barah": 12, "baarah": 12, "terah": 13, "chaudah": 14, "pandrah": 15,
    "solah": 16, "satrah": 17, "atharah": 18, "unnees": 19, "bees": 20, "pachees": 25, "tees": 30, "chalees": 40,
    "pachaas": 50, "pachas": 50, "sau": 100,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "छः": 6, "छे": 6, "सात": 7, "आठ": 8, "नौ": 9,
    "दस": 10, "ग्यारह": 11, "बारह": 12, "पंद्रह": 15, "बीस": 20, "पच्चीस": 25, "तीस": 30, "चालीस": 40, "पचास": 50, "सौ": 100,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100,
    "couple": 2, "dozen": 12, "single": 1, "alone": 1, "akela": 1, "akele": 1,
}
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

CITY_ALIASES = {
    "new delhi": "Delhi", "delhi ncr": "Delhi", "dilli": "Delhi", "दिल्ली": "Delhi", "नई दिल्ली": "Delhi",
    "bombay": "Mumbai", "मुंबई": "Mumbai", "मुम्बई": "Mumbai",
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru", "बेंगलुरु": "Bengaluru", "बैंगलोर": "Bengaluru", "बंगलौर": "Bengaluru",
    "madras": "Chennai", "चेन्नई": "Chennai",
    "calcutta": "Kolkata", "कोलकाता": "Kolkata", "कलकत्ता": "Kolkata",
    "हैदराबाद": "Hyderabad", "poona": "Pune", "पुणे": "Pune", "अहमदाबाद": "Ahmedabad",
    "जयपुर": "Jaipur", "लखनऊ": "Lucknow", "नागपुर": "Nagpur", "सूरत": "Surat", "पटना": "Patna", "इंदौर": "Indore",
    "भोपाल": "Bhopal", "cochin": "Kochi", "कोच्चि": "Kochi", "कोचीन": "Kochi", "mysore": "Mysuru", "मैसूर": "Mysuru",
    "नासिक": "Nashik", "नाशिक": "Nashik", "baroda": "Vadodara", "वडोदरा": "Vadodara", "बड़ौदा": "Vadodara",
    "vizag": "Visakhapatnam", "विशाखापट्टनम": "Visakhapatnam", "लुधियाना": "Ludhiana", "कोयंबटूर": "Coimbatore",
    "कोयम्बटूर": "Coimbatore",
}


def is_devanagari(text: str) -> bool:
    return bool(DEVANAGARI.search(text or ""))


def other_indic_script(text: str) -> bool:
    """True for Bengali/Tamil/Telugu/... input: the advisor answers in English and offers Hindi or English."""
    return bool(OTHER_INDIC.search(text or "")) and not is_devanagari(text or "")


def is_hinglish(text: str) -> bool:
    words = [w.lower() for w in LATIN_WORD.findall(text or "")]
    return any(w in HINGLISH_MARKERS for w in words)


def detect_language(text: str, current: str = "en") -> str:
    """'hi' for Devanagari, 'hinglish' for Roman-script Hindi, 'en' otherwise. Short replies ("5", "yes", "ok")
    keep the current language instead of flipping it."""
    if is_devanagari(text):
        return "hi"
    if is_hinglish(text):
        return "hinglish"
    words = LATIN_WORD.findall(text or "")
    if len(words) >= 4 or other_indic_script(text):
        return "en"
    return current or "en"


def parse_count(value) -> int | None:
    """Turn 5, "5", "paanch", "पाँच लोग", "about 10 people", "just me" into an int; None if nothing numeric is there."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower().translate(DEVANAGARI_DIGITS)
    m = re.search(r"\d+", text)
    if m:
        return int(m.group())
    if re.search(r"\b(just me|only me|myself|sirf main|main akela|main akeli)\b", text):
        return 1
    for token in re.findall(r"[a-z]+|[ऀ-ॿ]+", text):
        if token in NUMBER_WORDS:
            return NUMBER_WORDS[token]
    return None


def normalise_city(city, known: dict[str, int] | None = None) -> str | None:
    """Map aliases and Hindi spellings to the dataset's city names; unknown cities pass through title-cased."""
    if not city or not str(city).strip():
        return None
    raw = re.sub(r"[.,;!?()]+", " ", str(city)).strip()
    key = re.sub(r"\s+", " ", raw.lower())
    if key in CITY_ALIASES:
        return CITY_ALIASES[key]
    known = known or {}
    for name in known:
        if name.lower() == key:
            return name
    for alias, canonical in CITY_ALIASES.items():          # "Andheri, Mumbai" / "दिल्ली में"
        if re.search(rf"(?<![\wऀ-ॿ]){re.escape(alias)}(?![\wऀ-ॿ])", key):
            return canonical
    for name in known:
        if re.search(rf"\b{re.escape(name.lower())}\b", key):
            return name
    return raw.title()


def parse_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "haan", "ha", "han", "ji", "हाँ", "हां", "है", "registered", "active", "1"}:
        return True
    if text in {"false", "no", "n", "nahi", "nahin", "नहीं", "नही", "not yet", "none", "0"}:
        return False
    return None


# ---------- offline fact reader ----------
# Used only when no LLM provider is reachable, so an offline conversation still moves forward. It fills fields from
# explicit phrases ("6 staff", "two shops", "no GST", "in Pune") and, for bare answers ("5", "haan"), from the field
# the advisor just asked about. It never overrides a value the owner already gave.
STAFF_WORDS = r"(?:staff|people|persons?|employees?|workers?|teachers?|doctors?|log|logon|karmachari|लोग|कर्मचारी|आदमी|स्टाफ)"
SITE_WORDS = r"(?:shops?|stores?|outlets?|branch(?:es)?|offices?|clinics?|centres?|centers?|locations?|sites?|factor(?:y|ies)|units?|" \
             r"dukaan(?:ein|en)?|dukan(?:ein|en)?|दुकान(?:ें)?|ब्रांच|ऑफिस|शाखा(?:एं|ाएँ)?)"
COUNT_TOKEN = r"(\d+|[a-z]+|[ऀ-ॿ]+)"
NEED_WORDS = [
    (r"card machine|pos\b|upi|swipe|billing|कार्ड मशीन|पेमेंट", "pos_drops"),
    (r"whatsapp|व्हाट्सएप", "whatsapp_customers"),
    (r"camera|cctv|theft|chori|कैमरा|चोरी|सीसीटीवी", "cctv"),
    (r"\bemail|e-mail|ईमेल", "email_docs"),
    (r"virus|ransomware|malware|hack|firewall|data (?:safe|secur)|secur(?:e|ity) (?:the |our |my )?(?:network|computers?|pcs?|data|systems?|records)|"
     r"(?:computers?|pcs?|data|records|network) (?:safe|secure)|keep (?:our|my|the) (?:computers?|pcs?|data|records) safe|डेटा सुरक्षा", "data_security"),
    (r"all (?:the )?branches|one network|branches on", "multi_branch"),
    (r"machine (?:uptime|monitor)|monitor (?:the )?machines", "machines"),
    (r"vehicle|delivery van|truck|fleet|गाड़ी", "vehicles"),
    (r"website|online presence|found online|वेबसाइट", "website"),
    (r"never goes? down|never down|always on|backup internet|downtime|बंद नहीं|बार-बार बंद|baar baar band", "uptime"),
    (r"only (?:want )?sims?|just (?:want )?(?:\d+ )?(?:business )?sim|sirf sim", "sim_only"),
    (r"already have (?:an? )?(?:internet|broadband|connection|line)|have (?:my|our) own (?:internet|broadband)|internet from (?:a |another |local |some )|"
     r"keep (?:my|our) (?:current |existing )?(?:internet|broadband|connection)|apna internet hai|pehle se internet|पहले से इंटरनेट|अपना इंटरनेट", "services_only"),
]
NO_NEED = re.compile(r"just (?:reliable |good |fast )?internet|only internet|bas internet|sirf internet|सिर्फ इंटरनेट|बस इंटरनेट", re.I)
GST_NO = re.compile(r"\b(?:no|not|without|don'?t have|nahi|nahin)\b[^.;,!?]{0,20}\bgst(?:in)?\b|\bgst(?:in)?\b[^.;,!?]{0,20}\b(?:nahi|nahin|not|no)\b|"
                    r"gst नहीं|जीएसटी नहीं|नहीं है gst", re.I)
GENERIC_BUSINESS = [
    (r"साड़ी|saree|sari", "sari shop"), (r"clinic|क्लिनिक", "clinic"), (r"factory|फैक्ट्री|manufactur", "factory"),
    (r"office|ऑफिस|दफ्तर", "office"), (r"\bshop\b|\bstore\b|dukaan|dukan|दुकान", "shop"),
]
GST_YES = re.compile(r"\bgst(?:in)?\b|जीएसटी", re.I)
GSTIN_IN_TEXT = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
DONT_KNOW = re.compile(r"don'?t know|do not know|not sure|no idea|just tell me|whatever|pata nahi|maloom nahi|पता नहीं|मालूम नहीं|कुछ भी", re.I)
CITY_AFTER_IN = re.compile(r"\b(?:in|at|near)\s+([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})?)")
NEGATING_BEFORE = re.compile(r"(?:\bnot|\bnahi|\bnahin|instead of|\bfrom|नहीं)\s*$", re.I)
NEED_NEG_BEFORE = re.compile(r"\b(?:don'?t|do not|no need|not|without|nahi|nahin|mat)\b[^.,;!?]{0,25}$", re.I)
NEED_NEG_AFTER = re.compile(r"^[^.,;!?]{0,20}(?:\bnahi|\bnahin|\bnot needed|\bno need|नहीं|मत)", re.I)


def _needs_in(low: str) -> list[str]:
    """Needs named in the text, skipping negated mentions ("I don't need cameras", "कैमरा नहीं चाहिए")."""
    out = []
    for pattern, need in NEED_WORDS:
        for m in re.finditer(pattern, low):
            if NEED_NEG_BEFORE.search(low[:m.start()]) or NEED_NEG_AFTER.search(low[m.end():]):
                continue
            out.append(need)
            break
    return list(dict.fromkeys(out))


def _count_near(text: str, words: str) -> int | None:
    """First number attached to a staff/site word. Tries every match so "my staff" cannot hide "4 people"."""
    for m in re.finditer(COUNT_TOKEN + r"\s*(?:hi\s+|ही\s+)?" + words, text):
        n = parse_count(m.group(1))
        if n:
            return n
    for m in re.finditer(words + r"\s*(?:are|hain|है|हैं|:)?\s*" + COUNT_TOKEN, text):
        n = parse_count(m.group(1))
        if n:
            return n
    return None


def read_facts(text: str, pending: str | None, cities: dict[str, int], business_types: list[str], strict: bool = False) -> dict:
    """Facts stated in one owner message, as update_profile arguments.

    strict=True (used alongside a live LLM) keeps only the unambiguous readings: known cities only (no "in <Word>"
    guess), dataset business types only (no generic "shop"), and nothing from questions ("do I need GST?")."""
    if strict and "?" in (text or ""):
        return {}
    low = (text or "").lower().translate(DEVANAGARI_DIGITS)
    out: dict = {}
    staff = _count_near(low, STAFF_WORDS)
    if staff:
        out["employee_count"] = staff
    sites = _count_near(low, SITE_WORDS)
    if sites:
        out["num_sites"] = sites
    elif re.search(r"\b(?:one|ek|single|only one|ek hi)\s+(?:hi\s+)?" + SITE_WORDS, low) or re.search(r"एक\s*(?:ही\s*)?" + SITE_WORDS, low):
        out["num_sites"] = 1
    found: list[tuple[int, str]] = []
    for alias, canonical in CITY_ALIASES.items():
        for m in re.finditer(rf"(?<![\w\u0900-\u097F]){re.escape(alias)}(?![\w\u0900-\u097F])", low):
            found.append((m.start(), canonical))
    for name in cities:
        for m in re.finditer(rf"\b{re.escape(name.lower())}\b", low):
            found.append((m.start(), name))
    found = [(pos, c) for pos, c in found if not NEGATING_BEFORE.search(low[max(0, pos - 14):pos])]
    if found:
        out["city"] = max(found)[1]                              # the last city mentioned is the one they mean now
    elif not strict:
        m = CITY_AFTER_IN.search(text or "")
        if m and m.group(1).lower() not in {"india", "hindi", "english"}:
            out["city"] = normalise_city(m.group(1), cities)
    g = GSTIN_IN_TEXT.search((text or "").upper())
    if g:
        out["gstin"] = g.group()
    if GST_NO.search(low):
        out["has_gstin"] = False
    elif GST_YES.search(low):
        out["has_gstin"] = True
    for bt in sorted(business_types, key=len, reverse=True):
        if re.search(rf"\b{re.escape(bt)}\b", low):
            out["business_type"] = bt
            break
    if "business_type" not in out and not strict:
        for pattern, label in GENERIC_BUSINESS:
            if re.search(pattern, low):
                out["business_type"] = label
                break
    needs = _needs_in(low)
    if needs:
        out["needs"] = needs
    elif NO_NEED.search(low):
        out["no_specific_need"] = True
    # a bare answer to the question just asked ("5", "haan", "Pune")
    if pending and pending not in out:
        if pending in ("employee_count", "num_sites"):
            n = parse_count(low)
            if n:
                out[pending] = n
        elif pending == "has_gstin":
            b = parse_bool(low.split()[0] if low.split() else "")
            if b is not None:
                out["has_gstin"] = b
        elif pending == "business_type" and len(low.split()) <= 4 and low.strip():
            out["business_type"] = text.strip()
        elif pending == "city" and len(low.split()) <= 3 and low.strip():
            out["city"] = normalise_city(text, cities)
        elif pending == "needs" and low.strip():
            out["no_specific_need"] = True          # any answer to "what do you want solved" counts as answered
    return out
