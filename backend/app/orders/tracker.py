"""Order stages and expected dates. Install time comes from the bundle (the longest typical_install_days in it)."""
from datetime import date, datetime, timedelta

STAGES = ["PLACED", "VERIFIED", "PAID", "SCHEDULED", "INSTALLED", "ACTIVE"]

LABELS = {
    "PLACED": {"en": "Order placed", "hi": "ऑर्डर दर्ज"},
    "VERIFIED": {"en": "KYC verified", "hi": "KYC सत्यापित"},
    "PAID": {"en": "First payment received", "hi": "पहला भुगतान प्राप्त"},
    "SCHEDULED": {"en": "Installation scheduled", "hi": "इंस्टॉलेशन तय"},
    "INSTALLED": {"en": "Installed", "hi": "इंस्टॉल हो गया"},
    "ACTIVE": {"en": "Service active", "hi": "सेवा चालू"},
}


def eta(created: datetime | date, install_days: int) -> dict[str, str]:
    """Expected date (ISO) for each stage after PLACED."""
    d = created.date() if isinstance(created, datetime) else created
    install_days = max(1, int(install_days or 1))
    return {
        "PLACED": d.isoformat(),
        "VERIFIED": d.isoformat(),
        "PAID": d.isoformat(),
        "SCHEDULED": (d + timedelta(days=1)).isoformat(),
        "INSTALLED": (d + timedelta(days=install_days)).isoformat(),
        "ACTIVE": (d + timedelta(days=install_days + 1)).isoformat(),
    }


def next_stage(status: str) -> str:
    i = STAGES.index(status) if status in STAGES else 0
    return STAGES[min(i + 1, len(STAGES) - 1)]


def progress(status: str) -> float:
    i = STAGES.index(status) if status in STAGES else 0
    return i / (len(STAGES) - 1)
