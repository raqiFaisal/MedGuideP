"""Read the two 2023 SFDA open-data workbooks with their original row identities."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from openpyxl import load_workbook

SOURCE_LICENSE = "SFDA open-data terms (https://www.sfda.gov.sa/ar/open-data?page=2)"
SOURCES = {
    "local": ("SFDA 2023 registered human drugs (local)", "https://www.sfda.gov.sa/ar/node/284"),
    "nonlocal": ("SFDA 2023 registered human drugs (non-local)", "https://www.sfda.gov.sa/ar/node/285"),
}
COLUMNS = (
    "TradeName", "ScientificName", "Size", "SizeUnit", "DrugType", "DrugTypeAr",
    "LegalStatus", "LegalStatusAr", "Manufacturer_Name", "Manufacturer_Country",
)


def read_rows(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        rows = book["Data"].values
        if next(rows, ()) != COLUMNS:
            raise ValueError(f"Unexpected SFDA workbook columns: {path.name}")
        for number, row in enumerate(rows, 2):
            yield number, {
                key: str(value).strip() if value is not None else ""
                for key, value in zip(COLUMNS, row, strict=True)
            }
    finally:
        book.close()
