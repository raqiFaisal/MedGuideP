"""GTIN check-digit validation and conversion to GTIN-14 (GS1 mod-10).

Mirrored in ``mobile/src/text/gtin.ts``; both are tested against
``shared/fixtures/gtin.json``.
"""

from __future__ import annotations

SUPPORTED_LENGTHS = (8, 12, 13, 14)


def gs1_check_digit(body: str) -> int:
    """Check digit for a GTIN body (all digits except the last)."""
    total = 0
    for pos, ch in enumerate(reversed(body)):
        total += int(ch) * (3 if pos % 2 == 0 else 1)
    return (10 - total % 10) % 10


def is_valid_gtin(code: str) -> bool:
    code = code.strip()
    if len(code) not in SUPPORTED_LENGTHS or not (code.isascii() and code.isdigit()):
        return False
    return gs1_check_digit(code[:-1]) == int(code[-1])


def to_gtin14(code: str) -> str | None:
    """Return the zero-padded GTIN-14, or None if the code is not a valid GTIN."""
    code = code.strip()
    if not is_valid_gtin(code):
        return None
    return code.zfill(14)
