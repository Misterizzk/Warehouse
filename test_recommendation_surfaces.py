"""Concrete simulated destinations are visible wherever staff reads advice."""

import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from warehouse.database import connect
from warehouse.inventory import Inventory
from warehouse.inventory_table import recommendation_caption
from warehouse.live_monitor import LiveDetection, LiveSnapshot
from warehouse import live_ui
from warehouse.live_ui import current_item
from warehouse.session_ui import advice_for_result
from warehouse.sessions import Sessions
from warehouse.recommendations import RecommendationService
from warehouse.recommendation_data import recommendation_context
from warehouse.ui import Application, recommendation_rows


SIMULATED_ADVICE = {
    'code': 'MELEWATI_BATAS',
    'title': 'Periksa barang segera',
    'reason': 'Umur 120 hari melebihi batas.',
    'next_action': 'Periksa kondisi fisik sebelum memilih tindak lanjut.',
    'priority': 3,
    'source': 'Simulasi',
    'options': [
        {'kind': 'customer', 'target': 'Customer A', 'title': 'Tawarkan ke Customer A',
         'reason': 'Material cocok dengan unit customer.',
         'next_action': 'Jika layak, tawarkan 2 unit ke Customer A.'},
        {'kind': 'site', 'target': 'Site C', 'title': 'Redistribusi ke Site C',
         'reason': 'Site C kekurangan stok.',
         'next_action': 'Jika layak, pertimbangkan transfer 3 unit ke Site C.'},
    ],
}

SAVED_CUSTOMER_ACTION = {
    'choice': 'Tawarkan ke customer', 'target_kind': 'customer', 'target_code': 'A',
    'action_status': 'Belum selesai', 'physical_condition': 'Layak',
    'reason': 'Barang layak ditawarkan.', 'officer': 'Petugas Uji',
    'decided_at': '2026-09-30T09:00:00+07:00', 'completed_at': None,
}


def labels_under(widget):
    labels = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Label):
            labels.append(child.cget('text'))
        labels.extend(labels_under(child))
    return labels


def combos_under(widget):
    combos = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Combobox):
            combos.append(child)
        combos.extend(combos_under(child))
    return combos


class RecommendationProjectionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = connect(Path(self.folder.name) / 'demo.db')
        self.addCleanup(self.db.close)
        with self.db:
            self.db.execute('''INSERT INTO locations
                (code,area,rack,"column","row",level) VALUES (?,?,?,?,?,?)''',
                ('A-B01-K01-R01-T01', 'A', 'B01', 1, 1, 1))
            self.db.execute('''INSERT INTO batches
                (id,material,description,plant,storage_location,location_code,received_date,stock)
                VALUES (?,?,?,?,?,?,?,?)''',
                ('TEST-RED', 'MAT-RED', 'Barang merah', 'BHT', 'PBHT',
                 'A-B01-K01-R01-T01', '2026-06-20', 4))
            self.db.execute('''INSERT INTO material_unit_compatibility (material,unit_model)
                VALUES (?,?)''', ('MAT-RED', 'MODEL-X'))
            self.db.execute('''INSERT INTO customer_demand (customer,unit_model,open_demand)
                VALUES (?,?,?)''', ('A', 'MODEL-X', 3))

    def test_data_barang_projection_includes_named_demo_customer(self):
        rows = Inventory(self.db).list_batches(today=date(2026, 9, 29))

        shown = recommendation_rows(self.db, rows, today=date(2026, 9, 29))

        self.assertEqual(shown[0]['recommendation']['source'], 'Simulasi')
        self.assertEqual(shown[0]['recommendation']['options'][0]['target'], 'A')
        self.assertEqual(shown[0]['recommendation']['options'][0]['kind'], 'customer')

    def test_data_barang_reads_one_context_for_batches_of_same_material(self):
        with self.db:
            self.db.execute('''INSERT INTO batches
                (id,material,description,plant,storage_location,location_code,received_date,stock)
                VALUES (?,?,?,?,?,?,?,?)''',
                ('TEST-RED-2', 'MAT-RED', 'Barang merah kedua', 'BHT', 'PBHT',
                 'A-B01-K01-R01-T01', '2026-06-20', 2))
        rows = Inventory(self.db).list_batches(today=date(2026, 9, 29))
        statements = []
        self.db.set_trace_callback(statements.append)
        try:
            recommendation_rows(self.db, rows, today=date(2026, 9, 29))
        finally:
            self.db.set_trace_callback(None)

        self.assertEqual(sum('FROM site_demand WHERE material=' in sql for sql in statements), 1)
        self.assertEqual(sum('FROM material_unit_compatibility c' in sql for sql in statements), 1)

    def test_live_projection_includes_named_demo_customer(self):
        shown = current_item(self.db, 'ID:TEST-RED', today=date(2026, 9, 29))

        self.assertEqual(shown['recommendation']['source'], 'Simulasi')
        self.assertEqual(shown['recommendation']['options'][0]['target'], 'A')

    def test_draft_advice_updates_but_finished_result_keeps_check_snapshot(self):
        sessions = Sessions(self.db)
        key = sessions.start('Petugas', 'A')
        sessions.add_code(key, 'ID:TEST-RED')
        checked = sessions.results(key)[0]
        self.assertEqual(checked['recommendation_at_check']['options'][0]['target'], 'A')
        with self.db:
            self.db.execute("DELETE FROM customer_demand WHERE customer='A'")
            self.db.execute('''INSERT INTO customer_demand (customer,unit_model,open_demand)
                VALUES (?,?,?)''', ('B', 'MODEL-X', 2))

        current = advice_for_result(self.db, sessions.get(key), checked)
        self.assertEqual(current['options'][0]['target'], 'B')
        sessions.finish(key)
        frozen = advice_for_result(self.db, sessions.get(key), checked)
        self.assertEqual(frozen['options'][0]['target'], 'A')


class RecommendationCaptionTests(unittest.TestCase):
    def test_inventory_table_names_primary_destination_before_staff_decides(self):
        row = {'stock': 4, 'recommendation': SIMULATED_ADVICE, 'latest_action': None}
        self.assertIn('Customer A', recommendation_caption(row))

    def test_live_refresh_detects_changed_destination_without_new_scan(self):
        changed = dict(SIMULATED_ADVICE, options=[
            dict(SIMULATED_ADVICE['options'][0], target='B', title='Tawarkan ke Customer B')])
        signature = getattr(live_ui, 'recommendation_signature', None)

        self.assertIsNotNone(signature)
        self.assertNotEqual(signature(SIMULATED_ADVICE), signature(changed))



class RecommendationSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Application(self.root, Path(self.folder.name) / 'demo.db')

    def tearDown(self):
        if self.root.winfo_exists():
            self.app.close()
        self.folder.cleanup()

    def test_data_barang_drawer_shows_both_destinations_and_simulation_label(self):
        self.app.show('Data Barang')
        item = dict(self.app.inventory.list_batches()[0])
        item['recommendation'] = SIMULATED_ADVICE
        item['latest_action'] = None

        self.app.show_item(item)

        shown = ' '.join(labels_under(self.app.drawer))
        self.assertIn('Customer A', shown)
        self.assertIn('Site C', shown)
        self.assertIn('Simulasi', shown)

    def test_data_barang_drawer_shows_target_selected_by_officer(self):
        self.app.show('Data Barang')
        item = dict(self.app.inventory.list_batches()[0])
        item['recommendation'] = SIMULATED_ADVICE
        item['latest_action'] = SAVED_CUSTOMER_ACTION

        self.app.show_item(item)

        self.assertIn('Tujuan keputusan: Customer A',
                      ' '.join(labels_under(self.app.drawer)))

    def test_live_row_shows_both_destinations_without_creating_inspection(self):
        self.app.show('Live')
        code = 'ID:DEMO-0001'
        detection = LiveDetection(code, (), 1.0, 1.0, True)
        item = dict(material='MAT-OLD', location_code='A-B01-K01-R01-T01',
                    age=120, stock=4, status='Melewati batas',
                    recommendation=SIMULATED_ADVICE, latest_action=None)

        self.app.live_page.update(LiveSnapshot(None, (detection,), (), True), {code: item})

        shown = self.app.live_page._rows[code]['advice'].cget('text')
        self.assertIn('Customer A', shown)
        self.assertIn('Site C', shown)
        self.assertIn('Simulasi', shown)
        changed = dict(item, recommendation=dict(SIMULATED_ADVICE, options=[
            dict(SIMULATED_ADVICE['options'][0], target='B', title='Tawarkan ke Customer B')]))
        self.app.live_page.update(LiveSnapshot(None, (detection,), (), True), {code: changed})
        self.assertIn('Customer B', self.app.live_page._rows[code]['advice'].cget('text'))

    def test_live_row_shows_target_selected_by_officer(self):
        self.app.show('Live')
        code = 'ID:DEMO-0001'
        detection = LiveDetection(code, (), 1.0, 1.0, True)
        item = dict(material='MAT-OLD', location_code='A-B01-K01-R01-T01',
                    age=120, stock=4, status='Melewati batas',
                    recommendation=SIMULATED_ADVICE,
                    latest_action=dict(SAVED_CUSTOMER_ACTION, id=1))

        self.app.live_page.update(LiveSnapshot(None, (detection,), (), True), {code: item})

        self.assertIn('Customer A', self.app.live_page._rows[code]['decision'].cget('text'))
        changed = dict(item, latest_action=dict(SAVED_CUSTOMER_ACTION, id=1,
                                                 target_code='B'))
        self.app.live_page.update(LiveSnapshot(None, (detection,), (), True), {code: changed})
        self.assertIn('Customer B', self.app.live_page._rows[code]['decision'].cget('text'))

    def test_inspection_dialog_shows_both_destinations_and_simulation_label(self):
        self.app.show('Pengecekan')
        page = self.app.session_page
        key = page.service.start('Petugas Uji', 'Area A')
        page.open_session(key)
        page.code.set('DEMO-0001')
        page.add()
        page.table.choose('DEMO-0001')

        with patch('warehouse.session_ui.advice_for_result', return_value=SIMULATED_ADVICE):
            page.action_dialog()

        shown = ' '.join(labels_under(page.action_window))
        self.assertIn('Customer A', shown)
        self.assertIn('Site C', shown)
        self.assertIn('Simulasi', shown)
        self.root.geometry('1366x768')
        self.root.update()
        self.assertLessEqual(page.action_save.winfo_rooty() + page.action_save.winfo_height(),
                             self.root.winfo_screenheight())
        page.action_window.destroy()

    def test_many_destination_options_keep_save_button_visible_and_reason_accessible(self):
        self.root.deiconify()
        self.root.geometry('1366x768')
        self.app.show('Pengecekan')
        page = self.app.session_page
        key = page.service.start('Petugas Uji', 'Area A')
        page.open_session(key)
        page.code.set('DEMO-0001')
        page.add()
        page.table.choose('DEMO-0001')
        many_options = [dict(SIMULATED_ADVICE['options'][kind], target=target)
                        for kind in (0, 1) for target in ('A', 'B', 'C')]
        long_advice = dict(SIMULATED_ADVICE, options=many_options,
                           reason='Kebutuhan dan kecocokan barang perlu diperiksa. ' * 8,
                           next_action='Periksa fisik sebelum mengajukan relokasi atau penawaran. ' * 8)
        for scaling in (1.333333, 1.666667):
            with self.subTest(scaling=scaling):
                self.root.tk.call('tk', 'scaling', scaling)
                with patch('warehouse.session_ui.advice_for_result', return_value=long_advice):
                    page.action_dialog()
                self.root.update()
                win = page.action_window
                self.assertTrue(page.action_save.winfo_ismapped(),
                                'Tombol simpan hilang saat saran dan opsi panjang.')
                self.assertLessEqual(
                    page.action_save.winfo_rooty() + page.action_save.winfo_height(),
                    win.winfo_rooty() + win.winfo_height())
                page.reason_text.focus_force()
                self.root.update()
                self.assertGreaterEqual(page.reason_text.winfo_rooty(), win.winfo_rooty())
                self.assertLessEqual(
                    page.reason_text.winfo_rooty() + page.reason_text.winfo_height(),
                    page.action_save.winfo_rooty())
                win.destroy()

    def test_inspection_omits_target_actions_when_no_destination_is_known(self):
        self.app.show('Pengecekan')
        page = self.app.session_page
        key = page.service.start('Petugas Uji', 'Area A')
        page.open_session(key)
        page.code.set('DEMO-0001')
        page.add()
        page.table.choose('DEMO-0001')
        unknown_target_advice = dict(SIMULATED_ADVICE, options=[])

        with patch('warehouse.session_ui.advice_for_result',
                   return_value=unknown_target_advice):
            page.action_dialog()

        choices = tuple(value for combo in combos_under(page.action_window)
                        for value in combo['values'])
        self.assertNotIn('Tawarkan ke customer', choices)
        self.assertNotIn('Pindahkan ke site', choices)
        page.action_window.destroy()

    def test_inspection_can_choose_customer_destination_from_scenario(self):
        material = self.app.db.execute("SELECT material FROM batches WHERE id='DEMO-0001'").fetchone()[0]
        stock = self.app.db.execute("SELECT stock FROM batches WHERE id='DEMO-0001'").fetchone()[0]
        self.assertGreater(stock, 0)
        with self.app.db:
            self.app.db.execute("UPDATE batches SET received_date='2026-06-01' WHERE id='DEMO-0001'")
            self.app.db.execute('''INSERT OR IGNORE INTO material_unit_compatibility
                (material,unit_model) VALUES (?,?)''', (material, 'MODEL-UI-TEST'))
            self.app.db.execute('''INSERT OR REPLACE INTO customer_demand
                (customer,unit_model,open_demand) VALUES (?,?,?)''', ('A', 'MODEL-UI-TEST', 2))
        self.assertTrue(recommendation_context(self.app.db, material)['customers'])
        self.app.show('Pengecekan')
        page = self.app.session_page
        key = page.service.start('Petugas Uji', 'Area A')
        page.open_session(key)
        page.code.set('DEMO-0001')
        page.add()
        page.table.choose('DEMO-0001')
        self.assertTrue(advice_for_result(self.app.db, page.service.get(key), page.selected)['options'])
        page.action_dialog()

        combos = combos_under(page.action_window)
        self.assertTrue(any('Tawarkan ke customer' in box['values'] for box in combos))
        page.choice_var.set('Tawarkan ke customer')
        self.assertTrue(any('Customer A' in box['values'] for box in combos),
                        [box['values'] for box in combos])
        page.condition_var.set('Layak')
        page.target_var.set('Customer A')
        page.reason_text.insert('1.0', 'Kondisi fisik layak untuk penawaran.')
        page.action_save.invoke()

        decision = RecommendationService(self.app.db).for_result(key, 'DEMO-0001')
        self.assertEqual(decision['choice'], 'Tawarkan ke customer')
        self.assertEqual((decision['target_kind'], decision['target_code']), ('customer', 'A'))
        page.service.finish(key)
        page.open_session(key)
        page.table.choose('DEMO-0001')
        page.action_dialog()
        self.assertIn('Tujuan keputusan: Customer A', ' '.join(labels_under(page.action_window)))
        page.action_window.destroy()

    def test_reopened_draft_can_replace_a_customer_no_longer_recommended(self):
        material = self.app.db.execute(
            "SELECT material FROM batches WHERE id='DEMO-0001'").fetchone()[0]
        with self.app.db:
            self.app.db.execute("UPDATE batches SET received_date='2026-06-01' WHERE id='DEMO-0001'")
            self.app.db.execute('INSERT INTO material_unit_compatibility VALUES(?,?)',
                                (material, 'MODEL-CHANGE'))
            self.app.db.execute('INSERT INTO customer_demand VALUES(?,?,?)',
                                ('A', 'MODEL-CHANGE', 3))
        self.app.show('Pengecekan')
        page = self.app.session_page
        key = page.service.start('Petugas Uji', 'Area A')
        page.open_session(key)
        page.code.set('DEMO-0001')
        page.add()
        service = RecommendationService(self.app.db)
        first = service.save_decision(key, 'DEMO-0001', 'Layak', 'Tawarkan ke customer',
                                      'Customer A membutuhkan barang.',
                                      target_kind='customer', target_code='A')
        with self.app.db:
            self.app.db.execute("DELETE FROM customer_demand WHERE unit_model='MODEL-CHANGE'")
            self.app.db.execute('INSERT INTO customer_demand VALUES(?,?,?)',
                                ('B', 'MODEL-CHANGE', 2))
        page.table.choose('DEMO-0001')
        page.action_dialog()

        self.assertIn('Customer B', page.target_combo['values'])
        self.assertNotIn('Customer A', page.target_combo['values'])
        self.assertEqual(page.target_var.get(), '')
        self.assertIn('SARAN APLIKASI TERKINI', ' '.join(labels_under(page.action_window)))
        page.target_var.set('Customer B')
        page.reason_text.delete('1.0', 'end')
        page.reason_text.insert('1.0', 'Kebutuhan berubah; Customer B sesuai.')
        page.action_save.invoke()

        changed = service.for_result(key, 'DEMO-0001')
        self.assertEqual(changed['id'], first['id'])
        self.assertEqual(changed['target_code'], 'B')
        self.assertEqual(changed['recommendation_snapshot']['options'][0]['target'], 'B')


if __name__ == '__main__':
    unittest.main()
