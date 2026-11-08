"""Typed view of product_catalogue.csv. Everything the rules engine needs is parsed here once."""
from dataclasses import dataclass
from functools import lru_cache

from ..data.loader import connect


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    category: str
    description: str
    unit: str
    price_min: int
    price_max: int
    setup: int
    min_contract: int
    tiers: frozenset[int]
    min_employees: int
    min_sites: int
    requires_gstin: bool
    requires_one_of: frozenset[str]
    install_days: int
    segments: frozenset[str]

    @property
    def per_unit(self) -> bool:
        """True for items quoted per site / per user / per device / per camera."""
        return self.unit.lower().startswith("per ") and "month" not in self.unit.lower()


def _split(value: str | None, sep: str) -> frozenset[str]:
    return frozenset(x.strip() for x in (value or "").split(sep) if x.strip())


def _int(value: str | None, default: int = 0) -> int:
    try:
        return int(float(value)) if value not in (None, "") else default
    except ValueError:
        return default


@lru_cache
def catalogue() -> dict[str, Product]:
    rows = connect().execute("SELECT * FROM product_catalogue ORDER BY product_id").fetchall()
    out: dict[str, Product] = {}
    for r in rows:
        out[r["product_id"]] = Product(
            id=r["product_id"],
            name=r["product_name"],
            category=r["category"],
            description=r["description"],
            unit=r["unit"],
            price_min=_int(r["price_min_inr_per_month"]),
            price_max=_int(r["price_max_inr_per_month"]),
            setup=_int(r["one_time_setup_inr"]),
            min_contract=_int(r["min_contract_months"]),
            tiers=frozenset(int(t) for t in _split(r["available_city_tiers"], ";")),
            min_employees=_int(r["min_employees"], 1),
            min_sites=_int(r["min_sites"], 1),
            requires_gstin=(r["requires_gstin"] or "").upper() == "Y",
            requires_one_of=_split(r["requires_one_of"], "|"),
            install_days=_int(r["typical_install_days"], 1),
            segments=_split(r["target_segments"], ";"),
        )
    return out


@lru_cache
def city_tiers() -> dict[str, int]:
    """city -> tier, derived from the leads file (the only place tiers are given)."""
    rows = connect().execute("SELECT DISTINCT city, city_tier FROM smb_leads").fetchall()
    return {r["city"]: int(r["city_tier"]) for r in rows if r["city"]}


def tier_for_city(city: str | None, default: int = 2) -> int:
    if not city:
        return default
    tiers = city_tiers()
    if city in tiers:
        return tiers[city]
    # tolerant match: case-insensitive, ignore spaces
    key = city.strip().lower().replace(" ", "")
    for name, tier in tiers.items():
        if name.lower().replace(" ", "") == key:
            return tier
    return default
