"""Spreadsheet-safe text projection; never mutate source evidence or typed numbers."""
from __future__ import annotations

import csv
import io
import unicodedata
from collections.abc import Iterable, Mapping

_FORMULA = frozenset('=+-@＝＋－＠')


def safe_cell(value):
    """Keep numeric types numeric, force potentially executable external text to text.

    Quoting alone is insufficient. The apostrophe is an export-only text marker;
    recipients who remove it or re-save in other software can remove protection.
    """
    if not isinstance(value, str) or not value:
        return value
    probe = value
    while probe and (probe[0].isspace() or unicodedata.category(probe[0]) in {'Cc', 'Cf'}):
        probe = probe[1:]
    if value[0] in '\t\r\n' or (probe and probe[0] in _FORMULA):
        return "'" + value
    return value


def safe_dataframe(frame):
    """Copy a display/export projection, including otherwise downloadable columns."""
    result = frame.copy()
    result = result.map(safe_cell)
    result.columns = [safe_cell(c) for c in result.columns]
    result.index = result.index.map(safe_cell)
    return result


def csv_bytes(rows: Iterable[Mapping], columns: list[str]) -> bytes:
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\r\n')
    writer.writerow([safe_cell(c) for c in columns])
    for row in rows:
        writer.writerow([safe_cell(row.get(c, '')) for c in columns])
    return out.getvalue().encode('utf-8')
