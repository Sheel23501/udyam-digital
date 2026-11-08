import itertools

import pytest

from app.engine.bundles import recommend, validate, infer_segment
from app.engine.catalogue import catalogue
from app.engine.models import Need, Profile, Reason
from app.engine.rules import close_dependencies, eligible


def P(**kw) -> Profile:
    base = dict(business_type="Kirana store", employee_count=3, num_sites=1, city_tier=2, has_gstin=True, gstin_status="Active")
    base.update(kw)
    return Profile(**base)


# ---------- single rules ----------
@pytest.mark.parametrize(
    "pid,prof,reason",
    [
        ("P03", P(city_tier=2, employee_count=10), Reason.TIER_NOT_AVAILABLE),   # Fibre 1G is tier-1 only
        ("P03", P(city_tier=1, employee_count=4), Reason.MIN_EMPLOYEES),        # Fibre 1G needs 5 staff
        ("P21", P(employee_count=6), Reason.MIN_EMPLOYEES),                     # Firewall needs 10
        ("P05", P(employee_count=9), Reason.MIN_EMPLOYEES),                     # ILL 20 needs 10
        ("P06", P(employee_count=24), Reason.MIN_EMPLOYEES),                    # ILL 100 needs 25
        ("P12", P(employee_count=2), Reason.MIN_EMPLOYEES),                     # Cloud telephony needs 3
        ("P24", P(employee_count=9), Reason.MIN_EMPLOYEES),                     # Machine IoT needs 10
        ("P15", P(has_gstin=False), Reason.GSTIN_REQUIRED),                     # WhatsApp API
        ("P14", P(has_gstin=False), Reason.GSTIN_REQUIRED),                     # SMS
        ("P13", P(has_gstin=None), Reason.GSTIN_REQUIRED),                      # unknown GST = not yet usable
        ("P15", P(gstin_status="Cancelled"), Reason.GSTIN_NOT_ACTIVE),
        ("P13", P(gstin_status="Suspended"), Reason.GSTIN_NOT_ACTIVE),
    ],
)
def test_rule_fires(pid, prof, reason):
    assert eligible(catalogue()[pid], prof, set(), ignore_deps=True) == reason


def test_no_rule_fires_for_clean_cases():
    cat = catalogue()
    assert eligible(cat["P03"], P(city_tier=1, employee_count=5), set(), ignore_deps=True) is None
    assert eligible(cat["P21"], P(employee_count=10), {"P01"}) is None
    assert eligible(cat["P04"], P(has_gstin=False, employee_count=1), set()) is None


def test_dependency_rule_fires_only_without_base():
    cat = catalogue()
    assert eligible(cat["P23"], P(), set()) == Reason.NEEDS_BASE_LINE
    assert eligible(cat["P23"], P(), {"P04"}) is None          # CCTV may ride on AirFiber
    assert eligible(cat["P09"], P(), {"P04"}) == Reason.NEEDS_BASE_LINE   # failover may NOT
    assert eligible(cat["P09"], P(), {"P01"}) is None


# ---------- dependency closure ----------
def test_cctv_pulls_in_a_line():
    items, excluded, notes = close_dependencies({"P23": 2}, P(has_gstin=False))
    assert "P23" in items and items.keys() & {"P01", "P02", "P03", "P04", "P05", "P06"}
    assert any(n.type == "auto_added" and n.because_of == "P23" for n in notes)
    assert not excluded


def test_failover_upgrades_airfiber_to_fibre():
    items, excluded, notes = close_dependencies({"P04": 1, "P09": 1}, P(has_gstin=False))
    assert "P04" not in items and "P09" in items and "P01" in items
    assert any(n.type == "replaced" and n.because_of == "P09" for n in notes)


def test_static_ip_upgrades_airfiber():
    items, _, notes = close_dependencies({"P04": 1, "P11": 1}, P())
    assert "P04" not in items and "P11" in items and items.keys() & {"P01", "P02", "P03"}


def test_wifi_with_leased_line_adds_broadband_not_swap():
    items, _, notes = close_dependencies({"P05": 1, "P22": 1}, P(employee_count=15))
    assert "P05" in items and "P22" in items and items.keys() & {"P01", "P02", "P03", "P04"}


def test_ineligible_dependent_is_excluded_not_fixed():
    items, excluded, _ = close_dependencies({"P21": 1}, P(employee_count=4))
    assert "P21" not in items and excluded[0].reason == Reason.MIN_EMPLOYEES


def test_unknown_product_is_excluded():
    _, excluded, _ = close_dependencies({"P99": 1}, P())
    assert excluded[0].reason == Reason.UNKNOWN_PRODUCT


# ---------- recommendation policy ----------
def test_gst_free_path_offers_website_instead_of_whatsapp_api():
    b = recommend(P(has_gstin=False, needs=[Need.WHATSAPP]))
    ids = {i.product_id for i in b.items}
    assert "P15" not in ids and "P18" in ids
    assert {e.product_id: e.reason for e in b.excluded}["P15"] == Reason.GSTIN_REQUIRED


def test_sim_only_has_no_line():
    b = recommend(P(needs=[Need.SIM_ONLY]))
    ids = {i.product_id for i in b.items}
    assert ids & {"P07", "P08"} and not ids & {"P01", "P02", "P03", "P04", "P05", "P06"}


def test_services_only_excludes_firewall_with_reason():
    b = recommend(P(business_type="CA firm", employee_count=12, needs=[Need.SERVICES_ONLY, Need.EMAIL, Need.SECURITY]))
    ids = {i.product_id for i in b.items}
    assert "P16" in ids and "P20" in ids and not ids & {"P01", "P02", "P03", "P04", "P05", "P06"}
    assert {e.product_id: e.reason for e in b.excluded}.get("P21") == Reason.NEEDS_BASE_LINE


def test_requested_primary_line_is_used_as_base():
    b = recommend(P(business_type="Textile unit", employee_count=30, city_tier=2, requested_products=["P06"]))
    ids = {i.product_id for i in b.items}
    assert "P06" in ids and "P05" not in ids


def test_segment_inference_from_leads_data():
    assert infer_segment(Profile(business_type="Kirana store")) == "micro"
    assert infer_segment(Profile(business_type="Dental clinic")) == "prof"
    assert infer_segment(Profile(business_type="Gym chain")) == "multi"
    assert infer_segment(Profile(business_type="Packaging unit")) == "mfg"
    assert infer_segment(Profile(business_type="Something new", num_sites=4)) == "multi"


# ---------- invariant: whatever we recommend must pass our own validation ----------
GRID = list(itertools.product(
    ["Kirana store", "Dental clinic", "Gym chain", "Auto-parts unit", "Unknown business"],
    [1, 3, 6, 12, 30],                 # employees
    [1, 3],                            # sites
    [1, 2],                            # tier
    [False, True],                     # has_gstin
    [[], [Need.CCTV], [Need.POS_DROPS, Need.WHATSAPP], [Need.SECURITY, Need.EMAIL], [Need.BRANCHES, Need.CCTV], [Need.MACHINES], [Need.UPTIME], [Need.SIM_ONLY], [Need.SERVICES_ONLY, Need.SECURITY]],
))


@pytest.mark.parametrize("bt,emp,sites,tier,gst,needs", GRID)
def test_recommendation_never_violates_rules(bt, emp, sites, tier, gst, needs):
    prof = Profile(business_type=bt, employee_count=emp, num_sites=sites, city_tier=tier, has_gstin=gst, gstin_status="Active" if gst else None, needs=needs)
    b = recommend(prof)
    items = {i.product_id: i.qty for i in b.items}
    assert items, "empty bundle"
    result = validate(items, prof)
    assert result.violations == [], [v.model_dump() for v in result.violations]
    assert b.monthly_min > 0 and b.monthly_max >= b.monthly_min
    for e in b.excluded:
        assert e.reason in Reason and e.detail
    # a product never appears in both lists
    assert not (set(items) & {e.product_id for e in b.excluded})


def test_every_catalogue_product_can_be_recommended_somewhere():
    """Sanity: for each product there is at least one realistic profile that gets it (catches typos in NEED_MAP)."""
    cat = catalogue()
    seen: set[str] = set()
    for requested in ([], ["P03", "P05", "P06", "P11", "P12", "P13", "P14", "P22", "P25"]):
        for bt, emp, sites, tier, gst, needs in GRID:
            prof = Profile(business_type=bt, employee_count=emp, num_sites=sites, city_tier=tier, has_gstin=gst,
                           gstin_status="Active" if gst else None, needs=needs, requested_products=requested)
            seen |= {i.product_id for i in recommend(prof).items}
    assert set(cat) - seen == set(), f"never recommended: {sorted(set(cat) - seen)}"
