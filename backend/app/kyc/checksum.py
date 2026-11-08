"""GSTIN format and check-digit validation (standard GSTN algorithm; verified against all 3,534 registry GSTINs)."""
import re

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
# 2-digit state code, 5 letters, 4 digits, 1 letter (PAN), entity code, 'Z', check char.
# The dataset uses 'X' as the PAN 4th character, which [A-Z] accepts.
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def format_ok(gstin: str) -> bool:
    return bool(gstin) and bool(GSTIN_RE.match(gstin))


def check_char(first14: str) -> str | None:
    if len(first14) != 14 or any(c not in ALPHABET for c in first14):
        return None
    total = 0
    for i, ch in enumerate(first14):
        v = ALPHABET.index(ch) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return ALPHABET[(36 - total % 36) % 36]


def checksum_ok(gstin: str) -> bool:
    if not gstin or len(gstin) != 15:
        return False
    expected = check_char(gstin[:14])
    return expected is not None and expected == gstin[14]


def is_valid(gstin: str) -> bool:
    return format_ok(gstin) and checksum_ok(gstin)
