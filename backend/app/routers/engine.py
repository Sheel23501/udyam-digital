"""Direct access to the rules engine, for the quote screen and for judges' own scenarios."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..advisor.explain import explain
from ..advisor.tools import rec_payload
from ..engine.bundles import infer_segment, recommend, validate
from ..engine.catalogue import catalogue, tier_for_city
from ..engine.models import Profile
from ..engine.rules import eligible

router = APIRouter(tags=["engine"])


class ValidateIn(BaseModel):
    profile: Profile
    items: dict[str, int] = Field(..., description="{product_id: qty}; the owner's edited bundle")


@router.get("/catalogue")
def list_catalogue() -> list[dict]:
    return [{"id": p.id, "name": p.name, "category": p.category, "description": p.description, "unit": p.unit, "per_unit": p.per_unit,
             "price_min": p.price_min, "price_max": p.price_max, "setup": p.setup, "min_contract": p.min_contract,
             "install_days": p.install_days, "min_employees": p.min_employees, "min_sites": p.min_sites,
             "requires_gstin": p.requires_gstin, "requires_one_of": sorted(p.requires_one_of), "tiers": sorted(p.tiers)}
            for p in sorted(catalogue().values(), key=lambda p: p.id)]


@router.post("/engine/recommend")
def recommend_bundle(profile: Profile) -> dict:
    """Profile -> engine Bundle (plus the card payload and plain-language explanations in both languages)."""
    b = recommend(profile)
    return {**b.model_dump(mode="json"), "card": rec_payload(b), "segment": b.segment, "city_tier": tier_for_city(profile.city),
            "explanation": {"en": explain(b, "en"), "hi": explain(b, "hi")}}


@router.post("/engine/validate")
def validate_bundle(body: ValidateIn) -> dict:
    """Re-check an edited bundle on every toggle. Also returns which other catalogue items the owner could add."""
    v = validate(body.items, body.profile)
    cat = catalogue()
    known = {p: q for p, q in body.items.items() if p in cat and q > 0}
    addable = []
    for p in sorted(cat.values(), key=lambda p: p.id):
        if p.id in known:
            continue
        reason = eligible(p, body.profile, set(known))
        addable.append({"id": p.id, "name": p.name, "eligible": reason is None, "reason": reason.value if reason else None,
                        "price_min": p.price_min, "unit": p.unit})
    return {"violations": [x.model_dump(mode="json") for x in v.violations],
            "price": {"monthly_min": v.monthly_min, "monthly_max": v.monthly_max, "setup": v.setup,
                      "contract_months": v.contract_months, "install_days": v.install_days},
            "segment": infer_segment(body.profile), "addable": addable}
