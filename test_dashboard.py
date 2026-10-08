import tempfile
import tkinter as tk
import unittest
from datetime import date
from pathlib import Path
from warehouse.database import connect,seed_demo
from warehouse.dashboard import overview, aggregate_sections, aggregate_columns
from warehouse.rack_map import RackMap
from warehouse.locations import Locations
from warehouse.sessions import Sessions


class SectionProjectionTests(unittest.TestCase):
    def test_one_section_summarizes_all_three_levels_without_counting_zero_stock(self):
        cells = [
            dict(column=3, row=2, level=1, code='A-B01-K03-R02-T01',
                 rows=[dict(stock=3, status='Normal')]),
            dict(column=3, row=2, level=2, code='A-B01-K03-R02-T02',
                 rows=[dict(stock=1, status='Melewati batas')]),
            dict(column=3, row=2, level=3, code='A-B01-K03-R02-T03',
                 rows=[dict(stock=0, status='Warning')]),
            dict(column=2, row=2, level=1, code='A-B01-K02-R02-T01', rows=[]),
        ]
        sections = aggregate_sections(cells)

        selected = sections[(3, 2)]
        self.assertEqual([cell['level'] for cell in selected['cells']], [1, 2, 3])
        self.assertEqual((selected['status'], selected['batches'], selected['stock']),
                         ('Melewati batas', 2, 4))
        self.assertEqual(sections[(2, 2)]['status'], 'Tanpa stok')
        columns = aggregate_columns(sections)
        self.assertEqual((columns[3]['status'], columns[3]['batches'], columns[3]['stock']),
                         ('Melewati batas', 2, 4))
        self.assertEqual(columns[2]['status'], 'Tanpa stok')


class RackMapTests(unittest.TestCase):
    def test_seven_racks_cannot_navigate_before_first_page(self):
        root = tk.Tk()
        root.geometry('960x400')
        canvas = RackMap(root, lambda *args: None)
        canvas.pack(fill='both', expand=True)
        racks = {}
        for number in range(1, 8):
            key = ('A', f'B{number:02d}')
            sections = {(column, row): dict(column=column, row=row,
                        status='Normal', batches=1, stock=2, cells=[])
                        for column in range(1, 4) for row in range(1, 4)}
            racks[key] = dict(status='Normal', batches=9, stock=18,
                              sections=sections, cells=[])
        try:
            root.update()
            canvas.set_data(racks)
            root.update()

            def page_label():
                return [canvas.itemcget(item, 'text') for item in canvas.find_all()
                        if canvas.type(item) == 'text' and
                        canvas.itemcget(item, 'text') in ('-1 / 2', '0 / 2', '1 / 2', '2 / 2')]

            self.assertEqual(page_label(), ['1 / 2'])
            self.assertEqual(len(canvas.rack_bounds), 6)
            canvas.event_generate('<Button-1>', x=932, y=9)
            root.update()
            self.assertEqual(page_label(), ['2 / 2'])
            self.assertEqual(len(canvas.rack_bounds), 1)
            for attempt in range(1, 4):
                canvas.event_generate('<Button-1>', x=858, y=9)
                root.update()
                self.assertEqual(page_label(), ['1 / 2'], f'Previous click {attempt}')
            self.assertEqual(len(canvas.rack_bounds), 6)
        finally:
            root.destroy()

    def test_six_racks_show_nine_actionable_sections_each(self):
        root = tk.Tk()
        root.geometry('960x400')
        opened = []
        canvas = RackMap(root, lambda *args: opened.append(args))
        canvas.pack(fill='both', expand=True)
        racks = {}
        for area in ('A', 'B'):
            for number in range(1, 4):
                key = (area, f'B{number:02d}')
                sections = {(column, row): dict(column=column, row=row,
                            status='Normal', batches=1, stock=2, cells=[])
                            for column in range(1, 4) for row in range(1, 4)}
                racks[key] = dict(status='Normal', batches=9, stock=18,
                                  sections=sections, cells=[])
        try:
            root.update()
            canvas.set_data(racks)
            root.update()
            self.assertEqual(len(canvas.rack_bounds), 6)
            self.assertEqual(len(canvas.section_bounds), 54)
            rack_x0, rack_y0, rack_x1, _ = canvas.rack_bounds[('A', 'B01')]
            canvas.event_generate('<Button-1>', x=int((rack_x0+rack_x1)/2),
                                  y=int(rack_y0-11))
            root.update()
            self.assertEqual(opened, [], 'Rack heading must not open a column')
            bounds = canvas.section_bounds[(('A', 'B01'), 3, 2)]
            x0, y0, x1, y1 = bounds
            canvas.event_generate('<Button-1>', x=int((x0+x1)/2), y=int((y0+y1)/2))
            root.update()
            self.assertEqual(opened, [(('A', 'B01'), 3, 2)])
        finally:
            root.destroy()


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/'demo.db'
        self.db=connect(self.path)
        seed_demo(self.db,date(2026,9,16))

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_counts_filter_and_aging_reuse(self):
        data=overview(self.db,today=date(2026,9,16))
        self.assertEqual(len(data['active']),50)
        self.assertEqual([data['counts'][s] for s in ('Normal','Warning','Melewati batas')],[25,15,10])
        self.assertEqual(sum(r['batches'] for r in data['racks'].values()),50)
        area=overview(self.db,'A',date(2026,9,16))
        self.assertTrue(all(row['area']=='A' for row in area['rows']))
        self.assertEqual(area['total_stock'],sum(r['stock'] for r in area['active']))
        later=overview(self.db,today=date(2027,9,16))
        self.assertEqual(later['counts']['Melewati batas'],50)

    def test_independent_levels_aggregation_empty_and_zero(self):
        with self.db:
            self.db.execute("UPDATE batches SET location_code='B-B03-K03-R03-T03'")
            self.db.execute("UPDATE batches SET location_code='A-B01-K01-R01-T01' WHERE id='DEMO-0001'")
            self.db.execute("UPDATE batches SET location_code='A-B01-K01-R01-T02' WHERE id='DEMO-0041'")
        rack=overview(self.db,today=date(2026,9,16))['racks'][('A','B01')]
        cells={c['code']:c for c in rack['cells']}
        self.assertEqual(rack['status'],'Melewati batas')
        self.assertEqual(cells['A-B01-K01-R01-T01']['status'],'Normal')
        self.assertEqual(cells['A-B01-K01-R01-T02']['status'],'Melewati batas')
        self.assertEqual(cells['A-B01-K01-R01-T03']['status'],'Tanpa stok')
        self.assertEqual(rack['sections'][(1,1)]['status'],'Melewati batas')
        self.assertEqual(rack['columns'][1]['status'],'Melewati batas')
        with self.db:self.db.execute("UPDATE batches SET stock=0 WHERE id='DEMO-0041'")
        rack=overview(self.db,today=date(2026,9,16))['racks'][('A','B01')]
        self.assertEqual(rack['status'],'Normal')
        self.assertEqual(rack['sections'][(1,1)]['status'],'Normal')

    def test_persisted_highlight_and_historical_area(self):
        with self.db:
            self.db.execute("UPDATE batches SET location_code='A-B01-K01-R01-T01' WHERE id='DEMO-0041'")
        service=Sessions(self.db)
        key=service.start('Tester','warehouse',1,2)
        service.add_code(key,'DEMO-0041')
        location=service.results(key)[0]['location_code']
        with self.db:self.db.execute("UPDATE batches SET location_code='B-B03-K03-R03-T03' WHERE id='DEMO-0041'")
        service.add_code(key,'DEMO-0041')
        self.db.close()
        self.db=connect(self.path)
        data=overview(self.db)
        self.assertEqual(data['last']['location_code'],location)
        self.assertEqual(data['recent'][0]['location_code'],location)
        self.assertEqual(data['last_current_location_code'],'B-B03-K03-R03-T03')
        self.assertIsNone(overview(self.db,'A')['last_current_location_code'])
        self.assertEqual(overview(self.db,'B')['last_current_location_code'],'B-B03-K03-R03-T03')
        self.assertEqual(len(data['recent']),1)
        self.assertEqual(overview(self.db,'B')['recent'],[])

    def test_unknown_status_and_sparse_locations(self):
        Locations(self.db).add('C','B99',3,3,3)
        with self.db:self.db.execute("UPDATE batches SET received_date='bad',location_code='C-B99-K03-R03-T03' WHERE id='DEMO-0001'")
        data=overview(self.db,'C')
        self.assertEqual(data['counts']['Data perlu diperbaiki'],1)
        self.assertEqual(data['racks'][('C','B99')]['status'],'Data perlu diperbaiki')
        self.assertEqual(len(data['racks'][('C','B99')]['cells']),27)
        self.assertEqual(data['racks'][('C','B99')]['sections'][(3,3)]['status'],'Data perlu diperbaiki')
        self.assertEqual(overview(self.db,'Z')['rows'],[])


if __name__=='__main__':unittest.main()
