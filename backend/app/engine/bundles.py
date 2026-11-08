"""Recommendation policy: profile -> wanted products -> rules.close_dependencies -> priced Bundle.

Policy (what to suggest) lives here and may be tuned freely. Rules (what may be sold) live in rules.py and may not.
"""
import re
from functools import lru_cache

from ..data.loader import connect
from .catalogue import Product, catalogue
from .catalogue import tier_for_city
from .models import Bundle, Exclusion, Item, Need, Note, Profile, Reason, Segment, ValidationResult
from .rules import PRIMARY_LINES, close_dependencies, detail_for, eligible

SEGMENT_NAME_MAP = {
    "Micro retail & services": "micro",
    "Professional offices": "prof",
    "Small multi-site businesses": "multi",
    "Small manufacturers": "mfg",
}

KEYWORDS = {
    "mfg": ["unit", "manufactur", "factory", "moulding", "packaging", "textile", "auto parts", "fabrication", "engineering works", "mill"],
    "multi": ["chain", "franchise", "outlets", "stores", "branches", "multi"],
    "prof": ["clinic", "dental", "ca firm", "chartered", "law", "advocate", "coaching", "agency", "consult", "insurance",
             "diagnostic", "architect", "physio", "office", "studio", "accountant", "realty", "real estate", "travels"],
}

# need -> products the engine should try to include (eligibility decides what survives)
NEED_MAP: dict[Need, list[str]] = {
    Need.POS_DROPS: ["P09", "P19"],
    Need.WHATSAPP: ["P15"],
    Need.CCTV: ["P23"],
    Need.EMAIL: ["P16", "P17"],
    Need.SECURITY: ["P20", "P17", "P21"],
    Need.BRANCHES: ["P09", "P10", "P13"],
    Need.MACHINES: ["P24"],
    Need.VEHICLES: ["P25"],
    Need.WEBSITE: ["P18"],
    Need.UPTIME: ["P09"],
}

# if a product is excluded, offer this instead (GST-free alternatives)
FALLBACKS: dict[str, list[str]] = {"P15": ["P18"], "P14": ["P18"]}


@lru_cache
def business_type_segments() -> dict[str, str]:
    """business_type (lower) -> segment code, taken from the leads file (most common segment per type)."""
    rows = connect().execute(
        "SELECT business_type, segment, COUNT(*) AS n FROM smb_leads GROUP BY business_type, segment"
    ).fetchall()
    best: dict[str, tuple[str, int]] = {}
    for r in rows:
        bt = (r["business_type"] or "").strip().lower()
        seg = SEGMENT_NAME_MAP.get(r["segment"], "micro")
        if bt and (bt not in best or r["n"] > best[bt][1]):
            best[bt] = (seg, r["n"])
    return {k: v[0] for k, v in best.items()}


def infer_segment(prof: Profile) -> str:
    if prof.segment:
        return prof.segment.value if isinstance(prof.segment, Segment) else str(prof.segment)
    bt = (prof.business_type or "").strip().lower()
    table = business_type_segments()
    if bt in table:
        return table[bt]
    if bt:
        for known, seg in table.items():                      # whole-word match: "shop" is a shop, not a "workshop"
            if re.search(rf"\b{re.escape(bt)}\b", known) or re.search(rf"\b{re.escape(known)}\b", bt):
                return seg
    if (prof.num_sites or 1) >= 3:
        return "multi"
    for seg, words in KEYWORDS.items():
        if any(w in bt for w in words):
            return seg
    return "prof" if (prof.employee_count or 1) >= 8 else "micro"


def base_line(prof: Profile, seg: str) -> str:
    emp = prof.employee_count or 1
    tier = prof.city_tier or 2
    gst = bool(prof.has_gstin) and prof.gstin_status in (None, "Active")
    wants_fibre = any(n in prof.needs for n in (Need.CCTV, Need.POS_DROPS, Need.UPTIME))
    if seg == "micro":
        return "P01" if wants_fibre else "P04"          # AirFiber: 2-day install, cheapest; fibre when add-ons need it
    if seg == "prof":
        return "P03" if (tier == 1 and emp >= 5 and gst and Need.UPTIME in prof.needs) else "P02"
    if seg == "multi":
        return "P02" if emp >= 10 else "P01"
    if seg == "mfg":
        if emp >= 10 and gst:
            return "P05"
        return "P03" if (tier == 1 and gst and emp >= 5) else "P02"
    return "P01"


def qty_for(p: Product, prof: Profile, seg: str) -> int:
    emp = max(1, prof.employee_count or 1)
    sites = max(1, prof.num_sites or 1)
    unit = p.unit.lower()
    if p.id == "P24":                                   # machine monitoring: sensors, not people
        return max(4, emp // 2)
    if "site" in unit or "counter" in unit:
        return sites
    if "user" in unit or "device" in unit or "seat" in unit or "mailbox" in unit:
        return emp
    if "camera" in unit:
        return 2 * sites
    if "vehicle" in unit:
        return 2
    return 1


def sim_plan(seg: str, emp: int) -> tuple[str, int]:
    if seg == "micro":
        return "P07", (1 if emp <= 2 else 2)
    return "P08", max(2, min(emp // 4, 6))


def price_summary(items: dict[str, int]) -> dict:
    cat = catalogue()
    mn = sum(cat[p].price_min * q for p, q in items.items())
    mx = sum(cat[p].price_max * q for p, q in items.items())
    setup = sum(cat[p].setup * (q if "site" in cat[p].unit.lower() else 1) for p in items for q in [items[p]])
    contract = max((cat[p].min_contract for p in items), default=0)
    install = max((cat[p].install_days for p in items), default=0)
    return {"monthly_min": mn, "monthly_max": mx, "setup": setup, "contract_months": contract, "install_days": install}


def recommend(prof: Profile, line_for_addons: bool = False) -> Bundle:
    """Profile -> Bundle. With services_only the owner keeps their current internet, so dependents whose base line is
    missing are excluded rather than forcing a line; line_for_addons=True (owner agreed) lets the engine add just the
    cheapest eligible line those add-ons need, still without a default line or SIMs."""
    cat = catalogue()
    if prof.city or prof.city_tier not in (1, 2):
        prof.city_tier = tier_for_city(prof.city)
    seg = infer_segment(prof)
    emp = max(1, prof.employee_count or 1)
    sites = max(1, prof.num_sites or 1)
    requested = list(dict.fromkeys(prof.requested_products))      # keep order, drop duplicates; unknown IDs pass through
    services_only = Need.SERVICES_ONLY in prof.needs
    wanted: dict[str, int] = {}

    if Need.SIM_ONLY in prof.needs:
        sim, n = sim_plan(seg, emp)
        wanted[sim] = n
    elif services_only:
        pass                                             # owner keeps their current internet: no line, no SIMs unless asked
    else:
        # The owner's requested main line is used as the base if it is actually eligible; otherwise the default base is
        # used and the request is still recorded so it shows up in `excluded` with the reason.
        requested_primary = [p for p in requested if p in PRIMARY_LINES]
        base = base_line(prof, seg)
        if requested_primary and eligible(cat[requested_primary[0]], prof, set(), ignore_deps=True) is None:
            base = requested_primary[0]
        wanted[base] = sites
        sim, n = sim_plan(seg, emp)
        wanted[sim] = n

    if Need.SIM_ONLY not in prof.needs:
        for need in prof.needs:
            for pid in NEED_MAP.get(need, []):
                wanted.setdefault(pid, qty_for(cat[pid], prof, seg))
    for pid in requested:
        wanted.setdefault(pid, qty_for(cat[pid], prof, seg) if pid in cat else 1)

    items, excluded, notes = close_dependencies(wanted, prof, allow_auto_base=(not services_only) or line_for_addons)

    for ex in list(excluded):
        for fb in FALLBACKS.get(ex.product_id, []):
            if fb in cat and fb not in items and eligible(cat[fb], prof, set(items)) is None:
                items[fb] = qty_for(cat[fb], prof, seg)
                notes.append(Note(type="fallback", product_id=fb, because_of=ex.product_id,
                                  detail=f"Offered {cat[fb].name} instead of {cat[ex.product_id].name}"))

    ps = price_summary(items)
    return Bundle(segment=seg, items=[Item(product_id=p, qty=q) for p, q in items.items()], excluded=excluded, notes=notes, **ps)


def validate(items: dict[str, int], prof: Profile) -> ValidationResult:
    """Re-check a (possibly user-edited) bundle. Used by the quote screen on every toggle."""
    cat = catalogue()
    if prof.city or prof.city_tier not in (1, 2):
        prof.city_tier = tier_for_city(prof.city)
    violations: list[Exclusion] = []
    known = {p: q for p, q in items.items() if p in cat and q > 0}
    for pid in items:
        if pid not in cat:
            violations.append(Exclusion(product_id=pid, reason=Reason.UNKNOWN_PRODUCT, detail=f"{pid} is not a product we offer"))
    for pid in known:
        r = eligible(cat[pid], prof, set(known))
        if r:
            violations.append(Exclusion(product_id=pid, reason=r, detail=detail_for(cat[pid], r)))
    return ValidationResult(violations=violations, **price_summary(known))
