"""Recommendations with explicit simulated site and customer needs."""
import unittest
import tempfile
from datetime import date, timedelta
from pathlib import Path

from warehouse.database import connect, seed_demo
from warehouse.recommendations import RecommendationService, recommend_for
from warehouse.sessions import Sessions


TODAY = date(2026, 9, 29)


class RecommendationContextTests(unittest.TestCase):
    def test_green_recommends_only_site_with_rising_demand_and_shortage(self):
        item = {'received_date': '2026-09-10', 'stock': 10}
        context = {
            'source': 'Simulasi',
            'sites': [
                {'site': 'A', 'demand_prev': 10, 'demand_now': 13,
                 'open_demand': 8, 'site_stock': 3},
                {'site': 'B', 'demand_prev': 10, 'demand_now': 11,
                 'open_demand': 12, 'site_stock': 1},
                {'site': 'C', 'demand_prev': 10, 'demand_now': 15,
                 'open_demand': 4, 'site_stock': 7},
            ],
            'customers': [],
        }

        advice = recommend_for(item, today=TODAY, context=context)

        self.assertEqual(advice['code'], 'NORMAL')
        self.assertEqual(advice['source'], 'Simulasi')
        self.assertEqual([(option['kind'], option['target']) for option in advice['options']],
                         [('site', 'A')])
        self.assertIn('Site A', advice['next_action'])
        self.assertIn('5 unit', advice['options'][0]['reason'])

    def test_green_with_covered_site_needs_says_no_action(self):
        item = {'received_date': '2026-09-10', 'stock': 6}
        context = {'source': 'Simulasi',
                   'sites': [{'site': 'A', 'demand_prev': 10, 'demand_now': 13,
                              'open_demand': 3, 'site_stock': 8}],
                   'customers': []}

        advice = recommend_for(item, today=TODAY, context=context)

        self.assertEqual(advice['options'], [])
        self.assertIn('Aman', advice['title'])
        self.assertIn('belum perlu tindakan', advice['next_action'].lower())

    def test_green_stable_demand_does_not_claim_existing_shortage_is_covered(self):
        advice = recommend_for(
            {'received_date': '2026-09-10', 'stock': 6}, today=TODAY,
            context={'source': 'Simulasi', 'customers': [], 'sites': [
                {'site': 'A', 'demand_prev': 10, 'demand_now': 10,
                 'open_demand': 8, 'site_stock': 2}]})

        self.assertEqual(advice['options'], [])
        self.assertNotIn('terpenuhi', advice['next_action'].lower())
        self.assertIn('kriteria relokasi', advice['next_action'].lower())

    def test_yellow_names_compatible_customer_only_after_physical_check(self):
        item = {'received_date': '2026-07-15', 'stock': 8}
        context = {'source': 'Simulasi', 'sites': [],
                   'customers': [{'customer': 'B', 'unit_model': 'D85',
                                  'open_demand': 4}]}

        advice = recommend_for(item, today=TODAY, context=context)

        self.assertEqual(advice['code'], 'WARNING')
        self.assertEqual([(option['kind'], option['target']) for option in advice['options']],
                         [('customer', 'B')])
        self.assertIn('cek fisik', advice['next_action'].lower())
        self.assertIn('Customer B', advice['next_action'])
        self.assertIn('D85', advice['options'][0]['reason'])

    def test_red_lists_customer_then_shortage_site_as_alternative(self):
        item = {'received_date': '2026-06-20', 'stock': 10}
        context = {'source': 'Simulasi',
                   'customers': [{'customer': 'A', 'unit_model': 'PC200',
                                  'open_demand': 4}],
                   'sites': [{'site': 'C', 'demand_prev': 10, 'demand_now': 20,
                              'open_demand': 10, 'site_stock': 1}]}

        advice = recommend_for(item, today=TODAY, context=context)

        self.assertEqual(advice['code'], 'MELEWATI_BATAS')
        self.assertEqual([(option['kind'], option['target']) for option in advice['options']],
                         [('customer', 'A'), ('site', 'C')])
        self.assertIn('fisik', advice['next_action'].lower())
        self.assertIn('Customer A', advice['next_action'])
        self.assertIn('Site C', advice['next_action'])
        self.assertIn('jika layak', advice['next_action'].lower())

    def test_zero_stock_never_recommends_an_offer_or_transfer(self):
        context = {'source': 'Simulasi',
                   'sites': [{'site': 'A', 'demand_prev': 3, 'demand_now': 6,
                              'open_demand': 10, 'site_stock': 0}],
                   'customers': [{'customer': 'B', 'unit_model': 'D85',
                                  'open_demand': 5}]}

        advice = recommend_for({'received_date': '2026-06-20', 'stock': 0},
                               today=TODAY, context=context)

        self.assertEqual(advice['code'], 'STOK_HABIS')
        self.assertEqual(advice['source'], 'Simulasi')
        self.assertEqual(advice['options'], [])
        self.assertNotIn('Customer B', advice['next_action'])

    def test_invalid_inventory_never_recommends_a_destination(self):
        advice = recommend_for({'received_date': '2026-06-20', 'stock': -2},
                               today=TODAY,
                               context={'source': 'Simulasi',
                                        'sites': [{'site': 'A', 'demand_prev': 2,
                                                   'demand_now': 4, 'open_demand': 8,
                                                   'site_stock': 1}],
                                        'customers': []})

        self.assertEqual(advice['code'], 'DATA_PERLU_DIPERBAIKI')
        self.assertEqual(advice['options'], [])
        self.assertEqual(advice['source'], 'Simulasi')

    def test_red_without_need_data_does_not_invent_destination(self):
        advice = recommend_for({'received_date': '2026-06-20', 'stock': 8},
                               today=TODAY,
                               context={'source': 'Simulasi', 'sites': [], 'customers': []})

        self.assertEqual(advice['code'], 'MELEWATI_BATAS')
        self.assertEqual(advice['options'], [])
        self.assertIn('pemeriksaan fisik', advice['next_action'].lower())
        self.assertIn('tujuan belum', advice['next_action'].lower())
        self.assertNotIn('Site A', advice['next_action'])

    def test_red_site_shortage_is_not_described_as_rising_demand_when_falling(self):
        advice = recommend_for({'received_date': '2026-06-20', 'stock': 7},
                               today=TODAY,
                               context={'source': 'Simulasi', 'customers': [],
                                        'sites': [{'site': 'C', 'demand_prev': 10,
                                                   'demand_now': 8, 'open_demand': 9,
                                                   'site_stock': 2}]})

        self.assertEqual(advice['options'][0]['target'], 'C')
        self.assertIn('7 unit', advice['options'][0]['reason'])
        self.assertNotIn('naik', advice['options'][0]['reason'].lower())


class RecommendationSnapshotTests(unittest.TestCase):
    def test_decision_preserves_simulated_destinations_visible_to_officer(self):
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder) / 'context.db')
            try:
                seed_demo(db, today=TODAY)
                batch_id = 'DEMO-0041'
                material = db.execute('SELECT material FROM batches WHERE id=?',
                                      (batch_id,)).fetchone()[0]
                with db:
                    db.execute('''INSERT INTO site_demand VALUES(?,?,?,?,?,?)''',
                               (material, 'B', 8, 12, 9, 2))
                    db.execute('''INSERT INTO material_unit_compatibility VALUES(?,?)''',
                               (material, 'D85'))
                    db.execute('''INSERT INTO customer_demand VALUES(?,?,?)''',
                               ('A', 'D85', 3))
                session_id = Sessions(db).start('Petugas Demo', 'Area A')
                Sessions(db).add_code(session_id, batch_id)

                decision = RecommendationService(db).save_decision(
                    session_id, batch_id, 'Layak', 'Perlu dipindahkan',
                    'Kondisi fisik layak; petugas memilih relokasi.')

                self.assertEqual(decision['recommendation_snapshot']['source'], 'Simulasi')
                self.assertEqual([(option['kind'], option['target'])
                                  for option in decision['recommendation_snapshot']['options']],
                                 [('customer', 'A'), ('site', 'B')])
                self.assertIn('Customer A', decision['recommendation_next_action'])
                self.assertIn('Site B', decision['recommendation_next_action'])
            finally:
                db.close()

    def test_unmapped_material_decision_does_not_claim_simulated_need(self):
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder) / 'unmapped.db')
            try:
                seed_demo(db)
                batch_id = 'DEMO-0041'
                session_id = Sessions(db).start('Petugas Demo', 'Area A')
                Sessions(db).add_code(session_id, batch_id)

                decision = RecommendationService(db).save_decision(
                    session_id, batch_id, 'Layak', 'Tunda evaluasi',
                    'Belum ada data kebutuhan site atau customer.')

                self.assertNotIn('source', decision['recommendation_snapshot'])
                self.assertNotIn('options', decision['recommendation_snapshot'])
            finally:
                db.close()


class RecommendationTargetDecisionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = connect(Path(self.folder.name) / 'decision.db')
        self.addCleanup(self.db.close)
        seed_demo(self.db)
        location = self.db.execute('SELECT code FROM locations LIMIT 1').fetchone()[0]
        with self.db:
            for batch_id, material, days in (
                ('TARGET-GREEN', 'MAT-GREEN', 20),
                ('TARGET-YELLOW', 'MAT-YELLOW', 60),
                ('TARGET-NONE', 'MAT-NONE', 100),
            ):
                self.db.execute('INSERT INTO batches VALUES(?,?,?,?,?,?,?,?)',
                                (batch_id, material, material, 'BHT', 'PBHT',
                                 location, (date.today() - timedelta(days=days)).isoformat(), 10))
            self.db.execute('INSERT INTO site_demand VALUES(?,?,?,?,?,?)',
                            ('MAT-GREEN', 'A', 10, 13, 8, 3))
            self.db.execute('INSERT INTO material_unit_compatibility VALUES(?,?)',
                            ('MAT-YELLOW', 'D85'))
            self.db.execute('INSERT INTO customer_demand VALUES(?,?,?)',
                            ('B', 'D85', 4))

    def test_green_staff_can_choose_exact_recommended_site(self):
        session_id = Sessions(self.db).start('Petugas Demo', 'Area A')
        Sessions(self.db).add_code(session_id, 'TARGET-GREEN')

        decision = RecommendationService(self.db).save_decision(
            session_id, 'TARGET-GREEN', 'Layak', 'Pindahkan ke site',
            'Barang layak; ajukan Site A.', target_kind='site', target_code='A')

        self.assertEqual(decision['choice'], 'Pindahkan ke site')
        self.assertEqual((decision['target_kind'], decision['target_code']), ('site', 'A'))
        self.assertEqual(decision['recommendation_snapshot']['options'][0]['target'], 'A')

    def test_yellow_staff_can_offer_to_matching_customer(self):
        session_id = Sessions(self.db).start('Petugas Demo', 'Area A')
        Sessions(self.db).add_code(session_id, 'TARGET-YELLOW')

        decision = RecommendationService(self.db).save_decision(
            session_id, 'TARGET-YELLOW', 'Layak', 'Tawarkan ke customer',
            'Kondisi baik; ajukan penawaran.', target_kind='customer', target_code='B')

        self.assertEqual((decision['target_kind'], decision['target_code']), ('customer', 'B'))
        self.assertIn('Customer B', decision['recommendation_next_action'])

    def test_staff_cannot_select_target_absent_from_current_options(self):
        session_id = Sessions(self.db).start('Petugas Demo', 'Area A')
        Sessions(self.db).add_code(session_id, 'TARGET-GREEN')

        with self.assertRaisesRegex(ValueError, 'Tujuan tidak tersedia'):
            RecommendationService(self.db).save_decision(
                session_id, 'TARGET-GREEN', 'Layak', 'Pindahkan ke site',
                'Coba Site B.', target_kind='site', target_code='B')

        self.assertIsNone(RecommendationService(self.db).for_result(session_id, 'TARGET-GREEN'))

    def test_unfit_item_cannot_be_offered_or_transferred(self):
        session_id = Sessions(self.db).start('Petugas Demo', 'Area A')
        Sessions(self.db).add_code(session_id, 'TARGET-YELLOW')

        with self.assertRaisesRegex(ValueError, 'Layak'):
            RecommendationService(self.db).save_decision(
                session_id, 'TARGET-YELLOW', 'Tidak layak', 'Tawarkan ke customer',
                'Barang rusak.', target_kind='customer', target_code='B')

        self.assertIsNone(RecommendationService(self.db).for_result(session_id, 'TARGET-YELLOW'))

    def test_no_scenario_cannot_be_used_to_invent_target(self):
        session_id = Sessions(self.db).start('Petugas Demo', 'Area A')
        Sessions(self.db).add_code(session_id, 'TARGET-NONE')

        with self.assertRaisesRegex(ValueError, 'Tujuan tidak tersedia'):
            RecommendationService(self.db).save_decision(
                session_id, 'TARGET-NONE', 'Layak', 'Pindahkan ke site',
                'Tidak ada data kebutuhan.', target_kind='site', target_code='A')

        self.assertIsNone(RecommendationService(self.db).for_result(session_id, 'TARGET-NONE'))


if __name__ == '__main__':
    unittest.main()
