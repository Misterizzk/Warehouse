"""Narrow desktop regression check: python test_table_navigation_ui.py."""
import tkinter as tk
import unittest

from warehouse.inventory_table import InventoryTable


class TableNavigationTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.title('Warehouse Check - temporary navigation test')
        self.root.geometry('920x300')
        self.rows = [dict(id=f'TEST-{number:03d}', material=f'MAT-{number:03d}',
                          description='Navigation test', location_code='A-B01-K01-R01-T01',
                          stock=1, age=10, status='Normal') for number in range(30)]

    def tearDown(self):
        self.root.destroy()

    def table(self, callback):
        parent = tk.Frame(self.root)
        parent.pack(fill='both', expand=True)
        table = InventoryTable(parent, self.rows, callback)
        table.pack(fill='both', expand=True)
        self.root.update()
        return parent, table

    def test_navigation_retains_selection_callback_and_scroll(self):
        selected = []
        _, table = self.table(lambda row: selected.append(row['id']))
        self.assertEqual(table.move(1), 'break')
        self.assertEqual(table.selected, 'TEST-000')
        self.assertEqual(selected, ['TEST-000'])
        table.choose('TEST-029')
        self.assertEqual(table.move(-1), 'break')
        self.root.update()
        self.assertEqual(table.selected, 'TEST-028')
        self.assertEqual(selected[-1], 'TEST-028')
        self.assertGreater(table.canvas.yview()[0], 0)

    def test_navigation_callback_can_destroy_parent(self):
        for step in (-1, 1):
            with self.subTest(step=step):
                parent, table = self.table(lambda row: None)
                table.choose('TEST-015')
                selected = []

                def navigate(row):
                    selected.append(row['id'])
                    parent.destroy()

                table.on_select = navigate
                self.assertEqual(table.move(step), 'break')
                self.assertEqual(selected, [f'TEST-{15 + step:03d}'])
                self.assertFalse(table.winfo_exists())


if __name__ == '__main__':
    unittest.main()
