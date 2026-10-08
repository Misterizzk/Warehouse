import tempfile
import unittest
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from warehouse.database import connect, seed_demo
from warehouse.dashboard import overview
from warehouse.sessions import Sessions


class DashboardActivityTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.db=connect(Path(self.folder.name)/'demo.db')
        self.today=date(2026,9,21)
        seed_demo(self.db,self.today-timedelta(days=10))
        self.service=Sessions(self.db)

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def check(self, batch, day=None, officer='Tester', area='Warehouse'):
        key=self.service.start(officer,area)
        self.service.add_code(key,batch)
        moment=datetime.combine(day or self.today,time(12)).astimezone().isoformat()
        with self.db:
            self.db.execute('UPDATE check_results SET checked_at=? WHERE session_id=?',(moment,key))
        return key

    def test_empty_activity(self):
        result=overview(self.db,today=self.today)
        self.assertEqual(result['activity_today'],dict(checked_batches=0,result_count=0,draft_count=0))
        self.assertIsNone(result['latest_item'])

    def test_distinct_batch_count_date_filter_and_old_drafts(self):
        first=self.check('DEMO-0001')
        self.check('DEMO-0001')
        self.check('DEMO-0002')
        old=self.check('DEMO-0003',self.today-timedelta(days=1))
        with self.db:
            self.db.execute('UPDATE check_sessions SET started_at=? WHERE id=?',('2026-08-01T10:00:00+07:00',old))
        self.service.finish(first)
        result=overview(self.db,today=self.today)
        self.assertEqual(result['activity_today'],dict(checked_batches=2,result_count=3,draft_count=3))
        self.assertEqual(overview(self.db,today=self.today+timedelta(days=1))['activity_today']['checked_batches'],0)

    def test_area_uses_historical_location_and_drafts_are_global(self):
        with self.db:
            self.db.execute("UPDATE batches SET location_code='A-B01-K01-R01-T01' WHERE id='DEMO-0001'")
            self.db.execute("UPDATE batches SET location_code='B-B01-K01-R01-T01' WHERE id='DEMO-0002'")
        self.check('DEMO-0001',area='B')
        latest=self.check('DEMO-0002',officer='Operator B',area='A')
        with self.db:
            self.db.execute("UPDATE batches SET location_code='A-B03-K03-R03-T03',material='EDITED' WHERE id='DEMO-0002'")
        a=overview(self.db,'A',self.today)
        b=overview(self.db,'B',self.today)
        self.assertEqual(a['activity_today'],dict(checked_batches=1,result_count=1,draft_count=2))
        self.assertEqual(b['activity_today'],a['activity_today'])
        self.assertIsNone(a['latest_item'])
        item=b['latest_item']
        self.assertEqual(item['session_id'],latest)
        self.assertEqual(item['location_code'],'B-B01-K01-R01-T01')
        self.assertEqual(a['last_current_location_code'],'A-B03-K03-R03-T03')
        self.assertIsNone(b['last_current_location_code'])
        self.assertEqual(item['material'],'MAT-002')
        self.assertEqual(item['officer'],'Operator B')
        self.assertEqual(item['age'],self.service.results(latest)[0]['age'])
        self.assertEqual(item['status'],self.service.results(latest)[0]['status'])

    def test_today_uses_computer_timezone_and_counts_beyond_recent_five(self):
        for i in range(1,8):
            self.check(f'DEMO-{i:04d}')
        local_midnight=datetime.combine(self.today,time(0,15)).astimezone()
        utc_time=local_midnight.astimezone(timezone.utc).isoformat()
        with self.db:
            self.db.execute('UPDATE check_results SET checked_at=?',(utc_time,))
            self.db.execute("DELETE FROM metadata WHERE key='last_check'")
        result=overview(self.db,today=self.today)
        self.assertEqual(len(result['recent']),5)
        self.assertEqual(result['activity_today']['checked_batches'],7)
        self.assertEqual(result['activity_today']['result_count'],7)
        self.assertIsNotNone(result['latest_item'])


if __name__=='__main__':
    unittest.main()
