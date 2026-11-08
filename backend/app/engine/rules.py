"""Deterministic eligibility and dependency rules over the product catalogue.

This module is the only place that decides whether a product may be sold to a given business.
The LLM never overrides it; the quote re-runs it on every toggle. Keep it boring and fully tested.
"""
from .catalogue import Product, catalogue, tier_for_city
from .models import Exclusion, Note, Profile, Reason

PRIMARY_LINES = frozenset({"P01", "P02", "P03", "P04", "P05", "P06"})   # one of these is the business's main connection
FIBRE_OR_ILL = frozenset({"P01", "P02", "P03", "P05", "P06"})           # lines that add-ons like failover / firewall can attach to
MAX_DEPENDENCY_PASSES = 50


def resolve_tier(prof: Profile) -> int:
    """The city decides the tier; a caller-supplied tier is used only when no city is known."""
    if prof.city:
        return tier_for_city(prof.city)
    return prof.city_tier if prof.city_tier in (1, 2) else tier_for_city(None)


def eligible(p: Product, prof: Profile, bundle_ids: set[str], ignore_deps: bool = False) -> Reason | None:
    """Return the first rule the product breaks for this profile, or None if it can be sold."""
    if resolve_tier(prof) not in p.tiers:
        return Reason.TIER_NOT_AVAILABLE
    if (prof.employee_count or 1) < p.min_employees:
        return Reason.MIN_EMPLOYEES
    if (prof.num_sites or 1) < p.min_sites:
        return Reason.MIN_SITES
    if p.requires_gstin:
        if not prof.has_gstin:
            return Reason.GSTIN_REQUIRED
        if prof.gstin_status not in (None, "Active"):
            return Reason.GSTIN_NOT_ACTIVE
    if not ignore_deps and p.requires_one_of and not (p.requires_one_of & bundle_ids):
        return Reason.NEEDS_BASE_LINE
    return None


def detail_for(p: Product, r: Reason) -> str:
    cat = catalogue()
    if r == Reason.TIER_NOT_AVAILABLE:
        tiers = "/".join(str(t) for t in sorted(p.tiers))
        return f"{p.name} is only available in tier-{tiers} cities"
    if r == Reason.MIN_EMPLOYEES:
        return f"{p.name} needs at least {p.min_employees} staff"
    if r == Reason.MIN_SITES:
        return f"{p.name} needs at least {p.min_sites} locations"
    if r == Reason.GSTIN_REQUIRED:
        return f"{p.name} needs an active GST registration"
    if r == Reason.GSTIN_NOT_ACTIVE:
        return f"{p.name} needs an active GST registration; the one provided is not active"
    if r == Reason.NEEDS_BASE_LINE:
        names = ", ".join(cat[b].name for b in sorted(p.requires_one_of) if b in cat)
        return f"{p.name} needs one of these in the same bundle: {names}"
    if r == Reason.UNKNOWN_PRODUCT:
        return f"{p.id} is not a product we offer"
    return r.value


def cheapest_eligible(candidates: set[str] | frozenset[str], prof: Profile) -> str | None:
    cat = catalogue()
    ok = [cat[c] for c in candidates if c in cat and eligible(cat[c], prof, set(), ignore_deps=True) is None]
    return min(ok, key=lambda p: p.price_min).id if ok else None


def close_dependencies(wanted: dict[str, int], prof: Profile, allow_auto_base: bool = True) -> tuple[dict[str, int], list[Exclusion], list[Note]]:
    """Filter `wanted` {product_id: qty} by eligibility, then satisfy requires_one_of by adding (or upgrading to)
    the cheapest eligible base. With allow_auto_base=False (owner keeps their current internet), dependents whose
    base is missing are excluded instead of pulling in a line. Returns (bundle, excluded, notes)."""
    cat = catalogue()
    bundle: dict[str, int] = {}
    excluded: list[Exclusion] = []
    notes: list[Note] = []
    sites = max(1, prof.num_sites or 1)

    for pid, qty in wanted.items():
        if pid not in cat:
            excluded.append(Exclusion(product_id=pid, reason=Reason.UNKNOWN_PRODUCT, detail=f"{pid} is not a product we offer"))
            continue
        r = eligible(cat[pid], prof, set(), ignore_deps=True)
        if r:
            excluded.append(Exclusion(product_id=pid, reason=r, detail=detail_for(cat[pid], r)))
        else:
            bundle[pid] = max(1, int(qty))

    for _ in range(MAX_DEPENDENCY_PASSES):
        unmet = [pid for pid in sorted(bundle) if cat[pid].requires_one_of and not (cat[pid].requires_one_of & bundle.keys())]
        if not unmet:
            break
        pid = unmet[0]
        need = cat[pid].requires_one_of
        base = cheapest_eligible(need, prof) if allow_auto_base else None
        if base is None:
            del bundle[pid]
            excluded.append(Exclusion(product_id=pid, reason=Reason.NEEDS_BASE_LINE, detail=detail_for(cat[pid], Reason.NEEDS_BASE_LINE)))
            continue
        # Upgrade path: AirFiber (P04) cannot carry failover / firewall / static IP; swap it for the fibre line instead of adding a second line.
        if "P04" in bundle and "P04" not in need and base in FIBRE_OR_ILL:
            qty = bundle.pop("P04")
            bundle[base] = max(qty, sites)
            notes.append(Note(type="replaced", product_id=base, because_of=pid,
                              detail=f"Upgraded {cat['P04'].name} to {cat[base].name} because {cat[pid].name} needs a fibre line"))
        else:
            bundle[base] = sites
            notes.append(Note(type="auto_added", product_id=base, because_of=pid,
                              detail=f"Added {cat[base].name} because {cat[pid].name} needs it"))
    return bundle, excluded, notes
