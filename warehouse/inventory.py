"""Read model shared by shell and future inventory/dashboard features."""
from .domain import aging
from .locations import Locations
from uuid import uuid4
import re


class BatchValidationError(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


class Inventory:
    def __init__(self, db):
        self.db = db

    def validate(self, values):
        data = {}
        for field, label in (("material", "Material"), ("description", "Deskripsi"),
                             ("plant", "Plant"), ("storage_location", "Storage Location")):
            value = str(values.get(field, "")).strip()
            if not value or len(value) > 200:
                raise BatchValidationError(field, f"{label} wajib diisi, maksimal 200 karakter.")
            data[field] = value
        code = str(values.get("location_code", "")).strip().upper()
        try:
            Locations(self.db).require(code)
        except ValueError as exc:
            raise BatchValidationError("location_code", str(exc)) from exc
        data["location_code"] = code
        received = str(values.get("received_date", "")).strip()
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", received):
                raise ValueError()
            aging(received)
        except ValueError as exc:
            raise BatchValidationError("received_date", "Gunakan tanggal valid YYYY-MM-DD, tidak boleh setelah hari ini.") from exc
        data["received_date"] = received
        stock = str(values.get("stock", "")).strip()
        if not re.fullmatch(r"[0-9]{1,9}", stock):
            raise BatchValidationError("stock", "Stok harus bilangan bulat 0–999999999.")
        data["stock"] = int(stock)
        return data

    def add(self, values):
        data = self.validate(values)
        batch_id = "BAT-" + uuid4().hex.upper()
        with self.db:
            self.db.execute("""INSERT INTO batches
                (id,material,description,plant,storage_location,location_code,received_date,stock)
                VALUES (:id,:material,:description,:plant,:storage_location,:location_code,:received_date,:stock)""",
                dict(data, id=batch_id))
        return batch_id

    def update(self, batch_id, values, expected_stock=None):
        data = self.validate(values)
        with self.db:
            condition='id=:id'
            if expected_stock is not None:
                condition+=' AND stock=:expected_stock'
                data['expected_stock']=expected_stock
            result = self.db.execute("""UPDATE batches SET material=:material,description=:description,
                plant=:plant,storage_location=:storage_location,location_code=:location_code,
                received_date=:received_date,stock=:stock WHERE """+condition, dict(data, id=batch_id))
            if result.rowcount != 1:
                current=self.db.execute('SELECT stock FROM batches WHERE id=?',(batch_id,)).fetchone()
                if current is not None:
                    raise BatchValidationError('stock',f'Stok sudah berubah menjadi {current[0]} unit. Tutup formulir dan buka ulang Edit barang.')
                raise ValueError("Batch tidak ditemukan. Muat ulang Data Barang.")
        return batch_id

    def list_batches(self, today=None, query="", status="", location="", availability=""):
        result = []
        for row in self.db.execute('''SELECT b.*, l.area,l.rack,l."column" AS "column",l."row" AS "row",l.level
                                     FROM batches b JOIN locations l ON l.code=b.location_code ORDER BY b.id'''):
            item = dict(row)
            try:
                item["age"], item["status"] = aging(item["received_date"], today=today)
            except ValueError:
                item["age"], item["status"] = "—", "Data perlu diperbaiki"
            haystack = " ".join(str(item[k]) for k in ("id", "material", "description", "location_code", "plant", "storage_location"))
            if (query.strip().casefold() in haystack.casefold()
                    and (not status or item["status"] == status)
                    and (not location or item["location_code"] == location)
                    and (availability!='active' or item['stock']>0)
                    and (availability!='empty' or item['stock']==0)):
                result.append(item)
        return result
