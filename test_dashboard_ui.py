"""Desktop regression checks for the reference dashboard. Run on Windows with Tk."""
import tempfile
import tkinter as tk
from pathlib import Path

from warehouse.ui import Application
from warehouse.sessions import Sessions
from warehouse.locations import Locations


def inside(widget, container, context):
    """Check actual rendered bounds, including controls near the bottom/right edge."""
    assert widget.winfo_ismapped(), f'{context}: widget is not visible'
    x=widget.winfo_rootx()-container.winfo_rootx()
    y=widget.winfo_rooty()-container.winfo_rooty()
    width,height=widget.winfo_width(),widget.winfo_height()
    assert width>1 and height>1, f'{context}: no usable size {width}x{height}'
    assert x>=-2 and y>=-2, f'{context}: starts outside container ({x},{y})'
    assert x+width<=container.winfo_width()+2, f'{context}: exceeds right edge'
    assert y+height<=container.winfo_height()+2, f'{context}: bottom {y+height} exceeds container height {container.winfo_height()}'


with tempfile.TemporaryDirectory() as folder:
    for dpi in (96,120):
        root=tk.Tk()
        root.tk.call('tk','scaling',dpi/72)
        app=Application(root,Path(folder)/f'demo-{dpi}.db')
        # The test host may have a smaller physical screen; don't let WM clamp the
        # requested desktop geometries and silently repeat the same viewport.
        root.maxsize(3840,2160)
        try:
            failures=[]
            root.report_callback_exception=lambda *args:failures.append(args)
            service=Sessions(app.db)
            key=service.start('Tester','A')
            service.add_code(key,'DEMO-0041')
            code=service.results(key)[0]['location_code']
            rack_key=tuple(code.split('-')[:2])

            for width,height in ((1366,768),(1920,1080)):
                root.geometry(f'{width}x{height}')
                app.show('Dashboard')
                root.update()
                dashboard=app.dashboard_page
                context=f'{width}x{height} / {dpi} DPI'
                assert (root.winfo_width(),root.winfo_height())==(width,height),context+' viewport was clamped'
                assert len(dashboard.data['rows'])==50
                # A saved scan must not make B03 appear permanently selected
                # whenever the dashboard is reopened. Users can request it.
                assert dashboard.highlight is None
                assert dashboard.selected_rack is None
                assert dashboard.map_canvas.selected is None
                assert dashboard.data['activity_today']['checked_batches']==1
                inside(dashboard.metrics,app.body,context+' metrics')
                inside(dashboard.host,app.body,context+' dashboard host')
                for name in ('left','right','map_panel','info_panel','activity_panel'):
                    inside(getattr(dashboard,name),dashboard.host,context+' '+name)
                inside(dashboard.map_canvas,dashboard.map_panel,context+' map')
                inside(dashboard.scan_button,dashboard.right,context+' camera action')
                inside(dashboard.camera_canvas,dashboard.camera_panel,context+' camera preview')
                inside(dashboard.info_caption,dashboard.info_panel,context+' last check time')
                inside(dashboard.report_button,dashboard.activity_panel,context+' reports action')
                for field,label in dashboard.info_fields.items():
                    inside(label,dashboard.info_panel,context+' item '+field)
                    assert label.winfo_height()>=label.winfo_reqheight(),context+' clipped item '+field
                inside(dashboard.priority_tree,dashboard.left,context+' priority table')
                assert dashboard.map_canvas.winfo_height()>120,context+' map is too short'
                assert dashboard.camera_canvas.winfo_height()>=45,context+' camera preview is too short'
                assert dashboard.priority_tree.winfo_height()>50,context+' priority table is too short'
                assert len(dashboard.metrics.winfo_children())>=4

            for size in ('1366x700','1000x600'):
                root.geometry(size)
                root.update()
                dashboard.scroll_canvas.yview_moveto(1)
                dashboard.scroll_canvas.xview_moveto(1)
                root.update()
                inside(dashboard.report_button,dashboard.viewport,size+' reports reachable')
                dashboard.scroll_canvas.yview_moveto(0)
                root.update()
                inside(dashboard.scan_button,dashboard.viewport,size+' scan reachable')
            root.geometry('1366x768')
            root.update()

            dashboard.area.set('B')
            dashboard.reload()
            root.update()
            assert dashboard.data['racks']
            assert all(area=='B' for area,rack in dashboard.data['racks'])
            dashboard.focus_last()
            root.update()
            assert dashboard.area.get()=='Semua area'
            assert dashboard.highlight==code
            other_key=next(k for k in dashboard.data['racks'] if k!=rack_key)
            other_section=(other_key,1,1)
            x0,y0,x1,y1=dashboard.map_canvas.section_bounds[other_section]
            dashboard.map_canvas.event_generate('<Button-1>',x=int((x0+x1)/2),y=int((y0+y1)/2))
            root.update()
            assert dashboard.selected_rack==other_key
            assert dashboard.highlight is None
            assert dashboard.map_canvas.highlight is None
            dashboard.rack_window.destroy()
            # A section chooses its column slide; levels remain actionable there.
            section=(rack_key,3,2)
            assert section in dashboard.map_canvas.section_bounds
            x0,y0,x1,y1=dashboard.map_canvas.section_bounds[section]
            dashboard.map_canvas.event_generate('<Button-1>',x=int((x0+x1)/2),y=int((y0+y1)/2))
            root.update()
            assert dashboard.rack_window.winfo_exists()
            assert not failures,failures
            assert dashboard.selected_column==3
            assert dashboard.selected_row==2
            assert len(dashboard.cell_buttons)==9
            assert all('-K03-' in location for location in dashboard.cell_buttons)
            target=next(c for c in dashboard.data['racks'][rack_key]['cells']
                        if c['column']==3 and c['row']==2 and c['level']==1)
            rack_window=dashboard.rack_window
            dashboard.previous_column_button.invoke()
            root.update()
            assert dashboard.rack_window is rack_window
            assert dashboard.selected_column==2 and dashboard.selected_row==2
            assert all('-K02-' in location for location in dashboard.cell_buttons)
            dashboard.next_column_button.invoke()
            root.update()
            assert dashboard.selected_column==3
            dashboard.cell_buttons[target['code']].invoke()
            root.update()
            assert dashboard.location_window.winfo_exists()
            dashboard.location_window.destroy()
            dashboard.rack_window.destroy()

            assert dashboard.data['priorities']
            dashboard.open_item('DEMO-0041')
            root.update()
            assert app.page=='Data Barang'
            assert app.table.selected=='DEMO-0041'
            app.show('Dashboard')
            app.dashboard_page.open_report(key)
            root.update()
            assert app.page=='Laporan'
            assert app.report_page.data['session']['id']==key

            app.show('Dashboard')
            app.dashboard_page.start_check()
            root.update()
            assert app.page=='Pengecekan'
            app.session_page.start_window.destroy()

            Locations(app.db).create_rack('C','B99')
            app.show('Dashboard')
            dashboard=app.dashboard_page
            dashboard.area.set('C')
            dashboard.reload()
            root.update()
            assert list(dashboard.data['racks'])==[('C','B99')]
            dashboard.pick_section(('C','B99'),2,3)
            root.update()
            assert len(dashboard.cell_buttons)==9
            assert 'C-B99-K02-R03-T01' in dashboard.cell_buttons
            dashboard.cell_buttons['C-B99-K02-R03-T01'].invoke()
            root.update()
            assert dashboard.location_window.winfo_exists()
            assert not failures,failures
        finally:
            app.close()

print('Dashboard UI passed: 1366x768 and 1920x1080 at 96/120 DPI; captions and controls visible; smaller-window scroll; area/rack/item/report/session navigation')
