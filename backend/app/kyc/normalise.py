"""Position-aware clean-up of OCR confusables in identifiers. Fixes only what the format makes unambiguous
(a letter position cannot hold '0'); never guesses a different digit, so tampering still fails the checksum."""
import re

_TO_LETTER = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"})
_TO_DIGIT = str.maketrans({"O": "0", "I": "1", "S": "5", "B": "8", "Z": "2", "G": "6", "Q": "0", "D": "0"})

DIGIT_POSITIONS = (0, 1, 7, 8, 9, 10)      # state code + PAN digits
LETTER_POSITIONS = (2, 3, 4, 5, 6, 11)     # PAN letters


def clean_identifier(raw: str) -> str:
    """Upper-case and drop anything that is not a letter or digit (spaces, dashes, OCR noise)."""
    return "".join(ch for ch in (raw or "").upper() if ch.isalnum())


def normalise_gstin(raw: str) -> str:
    g = clean_identifier(raw)
    if len(g) != 15:
        return g
    chars = list(g)
    for i in DIGIT_POSITIONS:
        chars[i] = chars[i].translate(_TO_DIGIT)
    for i in LETTER_POSITIONS:
        chars[i] = chars[i].translate(_TO_LETTER)
    chars[13] = "Z"                        # always 'Z' by format; OCR often reads '2'
    return resolve_check_char("".join(chars))


_TWINS = {"0": "O", "O": "0", "1": "I", "I": "1", "5": "S", "S": "5", "8": "B", "B": "8", "2": "Z", "Z": "2", "6": "G", "G": "6"}


def resolve_check_char(g: str) -> str:
    """The 15th character may be a digit or a letter, so position rules cannot fix an OCR confusable there — but the
    check digit is computable from the first 14. If the read character is exactly the OCR twin of the computed one,
    use the computed one. Any other difference is left alone (and fails the checksum, as it should)."""
    from .checksum import check_char
    if len(g) != 15:
        return g
    expected = check_char(g[:14])
    if expected and g[14] != expected and _TWINS.get(g[14]) == expected:
        return g[:14] + expected
    return g


_UDYAM_RE = re.compile(r"UDYAM[-\s]*([A-Z]{2})[-\s]*(\d{2})[-\s]*(\d{7})")


def normalise_udyam(raw: str) -> str:
    """Return canonical UDYAM-XX-00-NNNNNNN, or the cleaned raw string if it does not look like a Udyam number."""
    s = (raw or "").upper().replace("—", "-").replace("–", "-")
    m = _UDYAM_RE.search(s.translate(str.maketrans({"O": "0", "I": "1"})).replace("UDYAM", "UDYAM"))
    if not m:
        return s.strip()
    return f"UDYAM-{m.group(1)}-{m.group(2)}-{m.group(3)}"


def normalise_name(s: str) -> str:
    """Lower-case, strip legal suffixes and punctuation, collapse spaces — for comparing business names."""
    s = (s or "").lower()
    s = re.sub(r"\b(llp|pvt\.? ?ltd\.?|private limited|limited|ltd\.?|opc)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def pin_code(address: str) -> str | None:
    """Indian PIN: 6 digits, tolerant of 'Kerala - 75 / 2083' style wraps (digits split by whitespace or slash)."""
    compact = re.sub(r"[\s/]", "", address or "")
    m = re.search(r"(?<!\d)(\d{6})(?!\d)", compact)
    return m.group(1) if m else None
