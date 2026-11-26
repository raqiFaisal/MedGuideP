"""Validate retail codes and the GS1 fields carried by medication packs."""
from __future__ import annotations

import calendar
import re
from datetime import date

from .text.gtin import to_gtin14

GS = "\x1d"
FIELDS = {"01": 14, "17": 6, "10": 0, "21": 0}


def parse_barcode(value: str) -> dict[str, str]:
    value = value.strip().removeprefix("]d2").removeprefix("]C1").lstrip(GS)
    direct = to_gtin14(value)
    if direct:
        return {"gtin": direct}
    pairs = []
    if value.startswith("("):
        matches = list(re.finditer(r"\((\d{2,4})\)", value))
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(value)
            pairs.append((match[1], value[match.end():end]))
    else:
        while value:
            ai = value[:2]
            if ai not in FIELDS:
                break
            value = value[2:]
            fixed = FIELDS[ai]
            if fixed:
                field, value = value[:fixed], value[fixed:]
                value = value.removeprefix(GS)
            else:
                field, _, value = value.partition(GS)
            pairs.append((ai, field))
    result: dict[str, str] = {}
    seen = set()
    for ai, field in pairs:
        if ai not in FIELDS:
            continue
        if ai in seen:
            return {}
        seen.add(ai)
        if ai == "01":
            if not re.fullmatch(r"[0-9]{14}", field) or not (gtin := to_gtin14(field)):
                return {}
            result["gtin"] = gtin
        elif ai == "17":
            if re.fullmatch(r"[0-9]{6}", field):
                year, month, day = 2000 + int(field[:2]), int(field[2:4]), int(field[4:])
                try:
                    result["expiry"] = date(year, month, day or calendar.monthrange(year, month)[1]).isoformat()
                except (ValueError, IndexError):
                    pass
        elif re.fullmatch(r"[A-Za-z0-9!%&'*+,./:;=<>?_-]{1,20}", field):
            result["lot" if ai == "10" else "serial"] = field
    return result if "gtin" in result else {}


def read_barcodes(rgb) -> list[dict[str, str]]:
    import numpy as np
    import zxingcpp

    formats = (zxingcpp.BarcodeFormat.DataMatrix, zxingcpp.BarcodeFormat.EAN13,
               zxingcpp.BarcodeFormat.EAN8, zxingcpp.BarcodeFormat.UPCA,
               zxingcpp.BarcodeFormat.Code128)
    reads = []
    for image in (rgb, np.ascontiguousarray(np.rot90(rgb))):
        codes = zxingcpp.read_barcodes(image, formats=formats, text_mode=zxingcpp.TextMode.Plain)
        decoded = {}
        for code in codes:
            if code.format in {zxingcpp.BarcodeFormat.DataMatrix, zxingcpp.BarcodeFormat.Code128} and not re.match(
                r"^(?:\]|\x1d|\(|01)", code.text
            ):
                continue
            if parsed := parse_barcode(code.text):
                decoded[parsed["gtin"]] = parsed
        reads.extend(decoded.values())
    return reads
