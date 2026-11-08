"""Tool schemas (OpenAI function-calling format) and their deterministic dispatch.

The model records facts with update_profile and asks for the bundle with get_recommendation. Everything that
reaches the model about products (bundle, prices, exclusions, notes) is produced here from engine output."""
import re

from ..engine.bundles import price_summary, recommend
from ..engine.catalogue import catalogue, city_tiers
from ..engine.models import Bundle, Need, Profile
from ..lookup.registry import gstin_lookup
from .language import normalise_city, parse_bool, parse_count
from .state import State

NEEDS = [n.value for n in Need]
REQUIRED = ("business_type", "employee_count", "num_sites", "city", "has_gstin")
PRODUCT_ID = re.compile(r"^p\s*0?(\d{1,2})$", re.I)

TOOLS = [
    {"type": "function", "function": {
        "name": "update_profile",
        "description": "Record facts the owner has told you. Call as soon as you learn something new; leave unknown fields out.",
        "parameters": {"type": "object", "properties": {
            "business_type": {"type": "string", "description": "e.g. kirana store, dental clinic, auto-parts unit"},
            "employee_count": {"type": "integer", "description": "people working there including the owner"},
            "num_sites": {"type": "integer", "description": "number of shops/offices/branches"},
            "city": {"type": "string", "description": "English city name, e.g. Delhi"},
            "has_gstin": {"type": "boolean", "description": "true if the business is GST registered"},
            "gstin": {"type": "string", "description": "15-character GSTIN if the owner gives one"},
            "current_internet": {"type": "string", "description": "what they use today, e.g. local cable broadband, mobile hotspot"},
            "monthly_spend": {"type": "integer", "description": "what they pay today per month in rupees"},
            "needs": {"type": "array", "items": {"type": "string", "enum": NEEDS},
                      "description": ("problems to solve: pos_drops = card machine/UPI/POS keeps dropping; whatsapp_customers = customers "
                                      "message/order on WhatsApp; cctv = cameras/theft; email_docs = business email/documents; "
                                      "data_security = protect PCs/records; multi_branch = several locations on one network; "
                                      "machines = factory machine monitoring; vehicles = delivery vehicles; sim_only = only mobile SIMs; "
                                      "website = be found online; uptime = internet must never go down; "
                                      "services_only = keeps current internet, wants only add-ons")},
            "no_specific_need": {"type": "boolean", "description": "true if the owner just wants internet/mobile with no particular problem"},
            "requested_products": {"type": "array", "items": {"type": "string"},
                                   "description": "catalogue IDs the owner asked for by name, e.g. [\"P21\"]"},
            "quantities": {"type": "object", "additionalProperties": {"type": "integer"},
                           "description": "owner-confirmed quantity overrides, e.g. {\"P23\": 50}"},
            "accept_accel_line": {"type": "boolean", "description": "true when the owner agrees to add an Accel line for their add-ons"},
            "preferred_language": {"type": "string", "enum": ["en", "hi", "hinglish"]},
        }, "required": []}}},
    {"type": "function", "function": {
        "name": "get_recommendation",
        "description": "Ask the rules engine for the bundle and price. Call once business type, staff count, number of locations, city, GST status and what they want solved are known. Never pick products yourself.",
        "parameters": {"type": "object", "properties": {
            "assume_defaults": {"type": "boolean", "description": "true only if the owner cannot answer: fills gaps conservatively (1 location, no GST)"},
        }, "required": []}}},
]


def _product_id(token: str) -> str | None:
    """'P21' / 'p 21' / 'Managed Firewall' -> 'P21'; None if it matches nothing in the catalogue."""
    cat = catalogue()
    t = str(token).strip()
    m = PRODUCT_ID.match(t)
    if m:
        pid = f"P{int(m.group(1)):02d}"
        return pid if pid in cat else None
    low = t.lower()
    for p in cat.values():
        if low == p.name.lower():
            return p.id
    for p in cat.values():
        if low and (low in p.name.lower() or p.name.lower() in low):
            return p.id
    return None


def rec_payload(b: Bundle, quantities: dict[str, int] | None = None) -> dict:
    """What the model is allowed to know about the bundle. Prices come from the catalogue via the engine."""
    cat = catalogue()
    items = {i.product_id: i.qty for i in b.items}
    overridden = {}
    if quantities:
        for pid, q in quantities.items():
            if pid in items and q and q > 0:
                items[pid] = int(q)
                overridden[pid] = int(q)
    price = price_summary(items) if overridden else {"monthly_min": b.monthly_min, "monthly_max": b.monthly_max, "setup": b.setup,
                                                      "contract_months": b.contract_months, "install_days": b.install_days}
    out = {
        "bundle": [{"id": pid, "name": cat[pid].name, "qty": q, "unit": cat[pid].unit, "price_from_per_unit": cat[pid].price_min}
                   for pid, q in items.items()],
        "monthly_from": price["monthly_min"],
        "monthly_upto": price["monthly_max"],
        "setup_one_time": price["setup"],
        "contract_months": price["contract_months"],
        "install_days": price["install_days"],
        "excluded": [{"id": e.product_id, "name": cat[e.product_id].name if e.product_id in cat else e.product_id,
                      "reason": e.reason.value, "why": e.detail} for e in b.excluded],
        "notes": [n.detail for n in b.notes],
    }
    if overridden:
        out["quantities_overridden"] = overridden
    return out


def missing_fields(prof: Profile, st: State | None = None) -> list[str]:
    """Facts still needed before a quote. 'needs' counts as known once the owner stated a problem, asked for a
    product, or said they have no specific need."""
    missing = [k for k in REQUIRED if getattr(prof, k) is None]
    if st is not None and not (prof.needs or prof.requested_products or st.needs_known):
        missing.append("needs")
    return missing


def compute(st: State) -> dict:
    """Run the engine for the current state; also propose the with-line alternative on a services-only ask."""
    st.recommendation = recommend(st.profile, line_for_addons=st.line_for_addons)
    out = rec_payload(st.recommendation, st.quantities)
    needs_line = [e for e in st.recommendation.excluded if e.reason.value == "NEEDS_BASE_LINE"]
    if needs_line and Need.SERVICES_ONLY in st.profile.needs and not st.line_for_addons:
        alt = recommend(st.profile, line_for_addons=True)
        have = {i.product_id for i in st.recommendation.items} | {e.product_id for e in needs_line}
        cat = catalogue()
        out["alternative_with_accel_line"] = {
            "adds": [cat[i.product_id].name for i in alt.items if i.product_id not in have],
            "unlocks": [cat[e.product_id].name for e in needs_line if e.product_id in cat],
            "bundle": [{"id": i.product_id, "name": cat[i.product_id].name, "qty": i.qty} for i in alt.items],
            "monthly_from": alt.monthly_min,
            "setup_one_time": alt.setup,
            "contract_months": alt.contract_months,
            "install_days": alt.install_days,
            "hint": "offer this in one sentence; if the owner agrees call update_profile with accept_accel_line=true",
        }
    if st.assumed:
        out["assumed"] = st.assumed
    st.allowed_numbers |= _numbers(out)
    return out


def _numbers(obj) -> set[int]:
    """Every integer in a tool payload: the figures the model is allowed to quote."""
    if isinstance(obj, bool):
        return set()
    if isinstance(obj, int):
        return {obj}
    if isinstance(obj, dict):
        return set().union(*(_numbers(v) for v in obj.values())) if obj else set()
    if isinstance(obj, list):
        return set().union(*(_numbers(v) for v in obj)) if obj else set()
    return set()


# Phrases owners use for specific catalogue products. Matched on the owner's own words so an explicit ask is never
# lost when the model forgets to pass requested_products. Generic words ("WhatsApp", "backup", "internet") are needs,
# not product asks, and are left to the model.
PRODUCT_PHRASES: list[tuple[str, str]] = [
    (r"\b(?:biz\s*)?fibre\s*1\s*g(?:bps)?\b|\b1\s*gbps\b|\b1000\s*mbps\b|\bgigabit\b", "P03"),
    (r"\bleased\s*line\s*100\b|\bill\s*100\b", "P06"),
    (r"\bleased\s*line\s*20\b|\bill\s*20\b", "P05"),
    (r"\bairfiber\b|\bair\s*fiber\b|\bair\s*fibre\b|\b5g\s*fwa\b", "P04"),
    (r"\bsd[\s-]?wan\b", "P10"),
    (r"\bstatic\s*ip\b", "P11"),
    (r"\bcloud\s*telephony\b|\bsip\s*trunk|\bivr\b", "P12"),
    (r"\btoll[\s-]?free\b|\b1800\s*number\b", "P13"),
    (r"\bbulk\s*sms\b|\bbusiness\s*sms\b|\bsms\s*pack\b", "P14"),
    (r"\bwhatsapp\s*(?:business\s*)?api\b|\bverified\s*whatsapp\b", "P15"),
    (r"\b(?:managed\s*)?firewall\b", "P21"),
    (r"\bsecure\s*wi-?fi\b|\bguest\s*(?:wi-?fi|network)\b", "P22"),
    (r"\bmachine\s*monitoring\b", "P24"),
    (r"\bfleet\s*track", "P25"),
]
NEGATION = re.compile(r"\b(?:don'?t|do not|no need|not|without|nahi|nahin|mat)\b[^.,;!?]{0,25}$", re.I)


def products_named_in(text: str) -> list[str]:
    """Catalogue IDs the owner asked for by name in this message, skipping negated mentions ("I don't want a firewall")."""
    found: list[str] = []
    low = (text or "").lower()
    for pattern, pid in PRODUCT_PHRASES:
        for m in re.finditer(pattern, low):
            if not NEGATION.search(low[:m.start()]):
                found.append(pid)
                break
    return list(dict.fromkeys(found))


def _update_profile(args: dict, st: State) -> dict:
    upd: dict = {}
    extra: dict = {}
    if args.get("business_type"):
        upd["business_type"] = str(args["business_type"]).strip()
    for k in ("employee_count", "num_sites", "monthly_spend"):
        if k in args and args[k] not in (None, ""):
            n = parse_count(args[k])
            if n is not None:
                upd[k] = max(1, n) if k != "monthly_spend" else max(0, n)
    if args.get("city"):
        upd["city"] = normalise_city(args["city"], city_tiers())
        upd["city_tier"] = None                               # re-derived by the engine from the new city
    if "has_gstin" in args and args["has_gstin"] not in (None, ""):
        b = parse_bool(args["has_gstin"])
        if b is not None:
            upd["has_gstin"] = b
            if not b:
                upd["gstin"] = None
                upd["gstin_status"] = None
    if args.get("gstin"):
        g = re.sub(r"[^0-9A-Za-z]", "", str(args["gstin"])).upper()
        upd["gstin"] = g
        row = gstin_lookup(g)
        if row:
            upd["has_gstin"] = True
            upd["gstin_status"] = row["status"]
            extra["gstin_registry"] = {"found": True, "status": row["status"], "legal_name": row["legal_name"], "state": row["state"]}
        else:
            upd["gstin_status"] = None
            extra["gstin_registry"] = {"found": False, "note": "not in the GST registry; it will be verified at KYC"}
    if args.get("current_internet"):
        upd["current_internet"] = str(args["current_internet"]).strip()
    if parse_bool(args.get("no_specific_need")):
        st.needs_known = True
    if "needs" in args and isinstance(args["needs"], list):
        st.needs_known = True
        valid = [Need(n) for n in args["needs"] if n in NEEDS]
        merged = list(dict.fromkeys(list(st.profile.needs) + valid))
        if Need.SERVICES_ONLY in valid and Need.SIM_ONLY in merged and Need.SIM_ONLY not in valid:
            merged.remove(Need.SIM_ONLY)
        upd["needs"] = merged
    if "requested_products" in args and isinstance(args["requested_products"], list):
        ids = []
        for tok in args["requested_products"]:
            pid = _product_id(tok)
            ids.append(pid if pid else str(tok).strip())      # unknown names pass through: the engine reports UNKNOWN_PRODUCT
        upd["requested_products"] = list(dict.fromkeys(list(st.profile.requested_products) + [i for i in ids if i]))
    if isinstance(args.get("quantities"), dict):
        for k, v in args["quantities"].items():
            pid = _product_id(k)
            n = parse_count(v)
            if pid and n:
                st.quantities[pid] = max(1, n)
    if "accept_accel_line" in args and args["accept_accel_line"] not in (None, ""):
        st.line_for_addons = bool(parse_bool(args["accept_accel_line"]))
    if args.get("preferred_language") in ("en", "hi", "hinglish"):
        st.language = args["preferred_language"]
        upd["language"] = st.language

    had_recommendation = st.recommendation is not None
    st.profile = st.profile.model_copy(update=upd)
    for k in list(st.assumed):                                # an answered field is no longer assumed
        if k in upd:
            st.assumed.pop(k, None)
    result = {"ok": True, "profile": {k: v for k, v in st.profile.model_dump(mode="json").items()
                                      if v not in (None, [], "") and k not in ("language", "city_tier")}, **extra}
    still = missing_fields(st.profile, st)
    if had_recommendation:
        result["recommendation"] = compute(st)
        result["note"] = "quote re-computed for the new facts: present it; do not call get_recommendation again"
    elif still:
        result["still_needed"] = still
        if still == ["needs"]:
            result["hint"] = "ask what problem they want solved (or set no_specific_need=true if they just want internet)"
    else:
        result["note"] = "all facts known: call get_recommendation now"
    return result


def _get_recommendation(args: dict, st: State) -> dict:
    missing = missing_fields(st.profile, st)
    if missing and not parse_bool(args.get("assume_defaults")):
        hint = ("ask the owner for these one at a time; only if they cannot answer, call again with assume_defaults=true"
                if missing != ["needs"] else
                "first ask what they want solved; if they just want internet, call update_profile with no_specific_need=true")
        return {"error": "missing_fields", "missing": missing, "hint": hint}
    if missing:
        defaults = {"business_type": "small business", "employee_count": 1, "num_sites": 1, "city": None, "has_gstin": False}
        fields = [k for k in missing if k in defaults]
        st.profile = st.profile.model_copy(update={k: defaults[k] for k in fields})
        st.assumed.update({k: defaults[k] for k in fields})
        st.needs_known = True
    return compute(st)


def dispatch(name: str, args: dict, st: State) -> dict:
    args = args if isinstance(args, dict) else {}
    if name == "update_profile":
        return _update_profile(args, st)
    if name == "get_recommendation":
        return _get_recommendation(args, st)
    return {"error": f"unknown tool {name}"}
