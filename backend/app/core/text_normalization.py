"""
===========================================================
HadiFlow
Text & Mobile Normalization Utilities
-----------------------------------------------------------
These utilities are the single source of truth for matching
customers across repeated lead submissions.

They handle the realities of Persian CRM data entry:
  * Persian digits (۰-۹) and Arabic digits (٠-٩) mixed with
    Latin digits inside mobile numbers
  * Country-code prefixes: +98, 0098, 98
  * Arabic letter variants: ي/ك/أ/إ/آ/ٱ/ة/ۀ/ؤ
  * Extra whitespace and half-space (ZWNJ) differences
===========================================================
"""
import re

# ----------------------------------------------------------
# Digit translation tables
# ----------------------------------------------------------
_PERSIAN_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_ARABIC_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# ----------------------------------------------------------
# Arabic/Persian character normalization
# Used for customer names so that "علي", "علی", "علی"
# all collapse into one comparable token.
# ----------------------------------------------------------
_CHARACTER_MAP = str.maketrans(
    {
        "ي": "ی",
        "ك": "ک",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ة": "ه",
        "ۀ": "ه",
        "ؤ": "و",
    }
)

# Zero-width non-joiner (نیم‌فاصله). Removed entirely so that
# "می شود" and "میشود" / "خانه" and "خان‌ه" compare equally.
_ZWNJ = "\u200c"


def normalize_mobile(raw: str | None) -> str | None:
    """
    Normalize a mobile number into a canonical digit string.

    Rules:
      1. Translate Persian/Arabic digits to Latin digits.
      2. Remove every non-digit character (spaces, dashes, +).
      3. Strip international prefixes: leading 0098, or leading
         98 when the result is an 12/13-digit international form.
      4. A 10-digit number starting with 9 is a mobile without
         the leading 0 -> prepend 0 (09xxxxxxxxx canonical form).

    Returns None when no digits can be extracted.
    """
    if raw is None:
        return None

    text = str(raw)
    text = text.translate(_PERSIAN_DIGIT_MAP)
    text = text.translate(_ARABIC_DIGIT_MAP)

    digits = re.sub(r"\D", "", text)
    if not digits:
        return None

    # International prefixes used in Iran
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98") and len(digits) in (12, 13):
        digits = digits[2:]

    # 9123456789 -> 09123456789
    if len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits

    return digits


def normalize_persian_text(raw: str | None) -> str | None:
    """
    Normalize Persian/Arabic free text (customer names, needs).

    Rules:
      1. Translate digits (names may contain digits).
      2. Normalize Arabic letter variants to their Persian forms.
      3. Remove zero-width non-joiners.
      4. Collapse all whitespace runs into single spaces and trim.

    Returns None for empty results.
    """
    if raw is None:
        return None

    text = str(raw)
    text = text.translate(_PERSIAN_DIGIT_MAP)
    text = text.translate(_ARABIC_DIGIT_MAP)
    text = text.translate(_CHARACTER_MAP)
    text = text.replace(_ZWNJ, "")
    text = re.sub(r"\s+", " ", text).strip()

    return text or None
