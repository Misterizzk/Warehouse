"""Shared rules; no UI or database dependencies."""
from datetime import date
import re

NORMAL_MAX = 30
AGE_LIMIT = 90


def location_code(area, rack, column, row, level):
    if not re.fullmatch(r"[A-Z]", area) or not re.fullmatch(r"[A-Z][0-9]{2}", rack):
        raise ValueError("Area harus A–Z dan rak seperti B03.")
    if any(type(value) is not int or not 1 <= value <= 3 for value in (column, row, level)):
        raise ValueError("Kolom, baris, dan tingkat harus 01–03.")
    return f"{area}-{rack}-K{column:02d}-R{row:02d}-T{level:02d}"


def legacy_code_to_new(code):
    """Translate an imported four-part address; never infer a missing rack."""
    match = re.fullmatch(r"([A-Z])-([A-Z][0-9]{2})-(\d{2})-(\d{2})", str(code).strip().upper())
    if not match:
        raise ValueError("Kode lokasi lama harus seperti A-B01-03-02.")
    area, rack, old_level, old_position = match.groups()
    return location_code(area, rack, int(old_position), 1, int(old_level))


def aging(received, today=None, normal_max=NORMAL_MAX, age_limit=AGE_LIMIT):
    if not 0 <= normal_max < age_limit:
        raise ValueError("Batas aging tidak valid.")
    entered = date.fromisoformat(received)
    days = ((today or date.today()) - entered).days
    if days < 0:
        raise ValueError("Tanggal masuk berada di masa depan.")
    return days, "Normal" if days <= normal_max else "Warning" if days <= age_limit else "Melewati batas"
