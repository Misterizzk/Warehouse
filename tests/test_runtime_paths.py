import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from warehouse.runtime_paths import application_root, database_path, resource_root

class RuntimePathTests(unittest.TestCase):
    def test_source_database_stays_in_existing_directory(self):
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(database_path(), Path(__file__).resolve().parents[1] / 'data' / 'warehouse_demo.db')

    def test_frozen_database_follows_executable(self):
        with tempfile.TemporaryDirectory(prefix='warehouse portable ') as folder:
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(Path(folder) / 'WarehouseCheck.exe')):
                self.assertEqual(application_root(), Path(folder).resolve())
                self.assertEqual(database_path(), Path(folder).resolve() / 'data' / 'warehouse_demo.db')
                self.assertNotEqual(application_root(), resource_root())

if __name__ == '__main__':
    unittest.main()
