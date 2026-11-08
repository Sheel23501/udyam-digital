"""Data models shared by the rules engine, the advisor and the API."""
from enum import Enum

from pydantic import BaseModel, Field


class Need(str, Enum):
    """What the owner says they want solved. The advisor maps free text to these; the engine maps these to products."""
    POS_DROPS = "pos_drops"              # card machine / UPI / POS keeps dropping
    WHATSAPP = "whatsapp_customers"      # customers message on WhatsApp, wants catalogue / API
    CCTV = "cctv"                        # watch the shop remotely, theft
    EMAIL = "email_docs"                 # business email, documents, staff accounts
    SECURITY = "data_security"           # protect PCs / records
    BRANCHES = "multi_branch"            # several locations, one bill, central control
    MACHINES = "machines"                # factory floor monitoring
    VEHICLES = "vehicles"                # delivery vehicles
    SIM_ONLY = "sim_only"                # just wants mobile plans
    WEBSITE = "website"                  # wants to be found online
    UPTIME = "uptime"                    # cannot afford downtime
    SERVICES_ONLY = "services_only"      # already has internet from someone else, wants only add-ons


class Segment(str, Enum):
    MICRO = "micro"
    PROF = "prof"
    MULTI = "multi"
    MFG = "mfg"


class Profile(BaseModel):
    business_type: str | None = None
    segment: Segment | None = None       # inferred from business_type / size if not given
    employee_count: int | None = Field(None, ge=1, le=100000)
    num_sites: int | None = Field(None, ge=1, le=10000)
    city: str | None = None
    city_tier: int | None = Field(None, ge=1, le=2)   # derived from the city whenever a city is given; unknown city -> tier 2
    has_gstin: bool | None = None
    gstin: str | None = None
    gstin_status: str | None = None      # Active | Cancelled | Suspended | None (= not verified yet)
    has_udyam: bool | None = None
    current_internet: str | None = None
    current_provider: str | None = None
    monthly_spend: int | None = None
    needs: list[Need] = Field(default_factory=list)
    requested_products: list[str] = Field(default_factory=list)   # explicit asks by catalogue ID
    language: str = "en"


class Reason(str, Enum):
    TIER_NOT_AVAILABLE = "TIER_NOT_AVAILABLE"
    MIN_EMPLOYEES = "MIN_EMPLOYEES"
    MIN_SITES = "MIN_SITES"
    GSTIN_REQUIRED = "GSTIN_REQUIRED"
    GSTIN_NOT_ACTIVE = "GSTIN_NOT_ACTIVE"
    NEEDS_BASE_LINE = "NEEDS_BASE_LINE"
    UNKNOWN_PRODUCT = "UNKNOWN_PRODUCT"


class Item(BaseModel):
    product_id: str
    qty: int = 1


class Exclusion(BaseModel):
    product_id: str
    reason: Reason
    detail: str


class Note(BaseModel):
    """Something the engine did on the owner's behalf that the advisor should explain as a benefit."""
    type: str                 # auto_added | replaced | fallback
    product_id: str
    because_of: str
    detail: str


class Bundle(BaseModel):
    segment: str
    items: list[Item]
    excluded: list[Exclusion]
    notes: list[Note]
    monthly_min: int
    monthly_max: int
    setup: int
    contract_months: int
    install_days: int


class ValidationResult(BaseModel):
    violations: list[Exclusion]
    monthly_min: int
    monthly_max: int
    setup: int
    contract_months: int
    install_days: int
