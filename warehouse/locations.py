"""Location operations shared by UI and future import workflows."""
import sqlite3
from .domain import location_code


def parse_location(area, rack, column, row, level):
    area, rack = str(area).strip().upper(), str(rack).strip().upper()
    try:
        # Accept integer text only, never truncate decimal inputs.
        values = (column, row, level)
        if any(not str(value).strip().isdigit() for value in values):
            raise ValueError
        column, row, level = (int(str(value).strip()) for value in values)
    except ValueError as exc:
        raise ValueError("Kolom, baris, dan tingkat harus bilangan bulat 01–03.") from exc
    return location_code(area, rack, column, row, level), area, rack, column, row, level


class Locations:
    def __init__(self, db):
        self.db = db

    def list(self):
        return self.db.execute('''SELECT l.*, count(b.id) AS batches FROM locations l
            LEFT JOIN batches b ON b.location_code=l.code
            GROUP BY l.code ORDER BY l.area,l.rack,l.column,l.row,l.level''').fetchall()

    def add(self, area, rack, column, row, level):
        values = parse_location(area, rack, column, row, level)
        try:
            with self.db:
                if self.db.execute("SELECT 1 FROM locations WHERE code=?", (values[0],)).fetchone():
                    raise ValueError(f"Lokasi {values[0]} sudah tersedia.")
                self.create_rack(values[1], values[2])
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Lokasi {values[0]} sudah tersedia.") from exc
        return values[0]

    def create_rack(self, area, rack):
        """Ensure a rack has all 27 addresses; safe to repeat for a partial rack."""
        _, area, rack, _, _, _ = parse_location(area, rack, 1, 1, 1)
        codes = []
        with self.db:
            for column in range(1, 4):
                for row in range(1, 4):
                    for level in range(1, 4):
                        code = location_code(area, rack, column, row, level)
                        self.db.execute('''INSERT OR IGNORE INTO locations(code,area,rack,column,row,level)
                            VALUES(?,?,?,?,?,?)''', (code, area, rack, column, row, level))
                        codes.append(code)
        return codes

    def choices(self):
        """Stable source for the batch-location selector in stage 4."""
        return [row['code'] for row in self.list()]

    def require(self, code):
        row = self.db.execute("SELECT * FROM locations WHERE code=?", (code,)).fetchone()
        if row is None:
            raise ValueError("Pilih lokasi yang terdaftar di Master Lokasi.")
        return row
