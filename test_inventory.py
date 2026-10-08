import tempfile
import unittest
from pathlib import Path
from datetime import date, timedelta
from warehouse.database import connect, seed_demo
from warehouse.inventory import Inventory, BatchValidationError
from warehouse.locations import Locations


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name)/'test.db'
        self.db = connect(self.path)
        seed_demo(self.db)
        self.service = Inventory(self.db)
        self.values = dict(material='00072', description='Test part', plant='BHT', storage_location='PBHT',
                           location_code='A-B01-K01-R01-T01', received_date=date.today().isoformat(), stock='12')

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_add_edit_restart_stable_id(self):
        key = self.service.add(self.values)
        second = self.service.add(self.values)
        self.assertNotEqual(key, second)  # Separate receipts may share material and date.
        location = Locations(self.db).add('C', 'B04', 3, 1, 2)
        self.service.update(key, dict(self.values, stock='0', location_code=location,
                                     received_date=(date.today()-timedelta(days=100)).isoformat()))
        self.db.close()
        self.db = connect(self.path)
        seed_demo(self.db)
        rows = Inventory(self.db).list_batches(query=key)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['id'], rows[0]['material'], rows[0]['stock'], rows[0]['status'], rows[0]['location_code']),
                         (key, '00072', 0, 'Melewati batas', location))
        self.assertEqual(len(Inventory(self.db).list_batches()), 52)

    def test_validation_atomic(self):
        key = self.service.add(self.values)
        for field, value in [('material',' '),('description',''),('plant',''),('storage_location',''),
                             ('stock','-1'),('stock','1.5'),('stock','1000000000'),
                             ('received_date','2026-02-30'),('received_date','2099-01-01'),
                             ('received_date','20260916'),('location_code','UNKNOWN')]:
            with self.subTest(field=field, value=value):
                with self.assertRaises(BatchValidationError):
                    self.service.update(key, dict(self.values, **{field:value}))
        self.assertEqual(self.service.list_batches(query=key)[0]['stock'], 12)
        with self.assertRaises(ValueError):
            self.service.update('missing', self.values)

    def test_combined_filters(self):
        key = self.service.add(self.values)
        rows = self.service.list_batches(query='test PART', status='Normal', location=self.values['location_code'])
        self.assertEqual([r['id'] for r in rows], [key])
        self.assertEqual(self.service.list_batches(query=key, status='Warning'), [])

    def test_stale_stock_edit_is_rejected_and_empty_filter(self):
        key=self.service.add(self.values)
        self.service.update(key,dict(self.values,stock='0'))
        with self.assertRaises(BatchValidationError):
            self.service.update(key,dict(self.values,description='Stale edit'),expected_stock=12)
        row=self.service.list_batches(query=key,availability='empty')[0]
        self.assertEqual(row['stock'],0)
        self.assertEqual(row['description'],self.values['description'])
        self.assertEqual(self.service.list_batches(query=key,availability='active'),[])


if __name__ == '__main__':
    unittest.main()
