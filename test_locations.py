import tempfile
import unittest
from pathlib import Path
from warehouse.database import connect,seed_demo
from warehouse.locations import Locations,parse_location
from warehouse.domain import legacy_code_to_new


class LocationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'demo.db'
        self.db=connect(self.path)
        seed_demo(self.db)
        self.service=Locations(self.db)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_add_normalize_and_reopen(self):
        before=[tuple(r) for r in self.db.execute('SELECT * FROM batches ORDER BY id')]
        code=self.service.add(' c ','b04','02','03','01')
        self.assertEqual(code,'C-B04-K02-R03-T01')
        self.db.close()
        self.db=connect(self.path)
        seed_demo(self.db)
        self.service=Locations(self.db)
        self.assertIn(code,self.service.choices())
        self.assertEqual(self.service.require(code)['level'],1)
        self.assertEqual(len([row for row in self.service.list() if row['area']=='C']),27)
        self.assertEqual(len(self.service.create_rack('C', 'B04')), 27)
        self.assertEqual(len([row for row in self.service.list() if row['area']=='C']),27)
        self.assertEqual(before,[tuple(r) for r in self.db.execute('SELECT * FROM batches ORDER BY id')])

    def test_duplicate_does_not_add(self):
        with self.assertRaisesRegex(ValueError,'sudah tersedia'):
            self.service.add('a','b01',1,1,1)
        self.assertEqual(len(self.service.list()),162)

    def test_invalid_and_unknown(self):
        for values in [('', 'B01',1,1,1),('A','B-01',1,1,1),('A','B01',0,1,1),
                       ('A','B01',1,100,1),('A','B01','1.5',1,1)]:
            with self.assertRaises(ValueError):parse_location(*values)
        with self.assertRaises(ValueError):self.service.require('unknown')
        self.assertEqual(sum(r['batches'] for r in self.service.list()),50)

    def test_legacy_translation_is_explicit(self):
        self.assertEqual(legacy_code_to_new('a-b01-03-02'), 'A-B01-K02-R01-T03')
        with self.assertRaises(ValueError):legacy_code_to_new('A-B01-04-02')


if __name__=='__main__':unittest.main()
