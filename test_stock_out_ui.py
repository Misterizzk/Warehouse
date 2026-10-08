"""Run separately on Windows: stock-out workflow against disposable databases."""
import tempfile
import tkinter as tk
from datetime import date
from pathlib import Path

from warehouse.dashboard import overview
from warehouse.ui import Application


def inside(widget, container, context):
    assert widget.winfo_ismapped(), context + ': control is not visible'
    x = widget.winfo_rootx() - container.winfo_rootx()
    y = widget.winfo_rooty() - container.winfo_rooty()
    assert widget.winfo_width() > 1 and widget.winfo_height() > 1, context
    assert x >= -2 and y >= -2, context + ': control starts outside the window'
    assert x + widget.winfo_width() <= container.winfo_width() + 2, context + ': exceeds right edge'
    assert y + widget.winfo_height() <= container.winfo_height() + 2, context + ': exceeds bottom edge'


def batch(app, key):
    return next(row for row in app.inventory.list_batches() if row['id'] == key)


def saved_count(app):
    return app.db.execute('SELECT count(*) FROM stock_movements').fetchone()[0]


def select_history(history, root):
    children = history.table.get_children()
    assert children, 'Saved stock-out movement is missing from history'
    history.table.selection_set(children[0])
    history.table.focus(children[0])
    history.table.event_generate('<<TreeviewSelect>>')
    root.update()
    return history.detail.get('1.0', 'end')


import subprocess
import sys
import unittest


def run_workflow():
    with tempfile.TemporaryDirectory() as folder:
        for dpi in (96, 120):
            database_path = Path(folder) / f'stock-{dpi}.db'
            root = tk.Tk()
            root.tk.call('tk', 'scaling', dpi / 72)
            app = Application(root, database_path)
            root.maxsize(3840, 2160)
            callback_errors = []
            root.report_callback_exception = lambda *args: callback_errors.append(args)
            key = 'DEMO-0002'
            try:
                original = batch(app, key)
                initial_active = len(overview(app.db)['active'])
                assert original['stock'] > 1
                for width, height in ((1366, 768), (1920, 1080), (1000, 600)):
                    root.geometry(f'{width}x{height}')
                    app.show('Data Barang')
                    app.table.choose(key)
                    root.update()
                    context = f'{width}x{height} / {dpi} DPI'
                    assert (root.winfo_width(), root.winfo_height()) == (width, height), context + ': viewport clamped'
                    inside(app.stock_out_button, root, context + ' stock-out action')
                    inside(app.stock_history_button, root, context + ' history action')
                    app.stock_out_button.invoke()
                    form = app.stock_out_window
                    root.update()
                    for name in ('save_button', 'remaining'):
                        inside(getattr(form, name), form, context + ' form ' + name)
                    form.reveal(form.note_text)
                    root.update()
                    inside(form.note_text, form.canvas, context + ' reachable note')
                    form.geometry('700x560')
                    root.update()
                    inside(form.save_button, form, context + ' compact form save')
                    form.reveal(form.inputs['officer'])
                    root.update()
                    inside(form.inputs['officer'], form.canvas, context + ' reachable officer')
                    form.destroy()

                root.geometry('1366x768')
                app.show_stock_out(key)
                form = app.stock_out_window
                form.values['quantity'].set('1')
                form.values['occurred_on'].set(date.today().isoformat())
                form.values['officer'].set('')
                form.save_button.invoke()
                root.update()
                assert form.winfo_exists(), 'Empty officer must leave the form open'
                assert saved_count(app) == 0
                assert batch(app, key)['stock'] == original['stock']

                form.values['officer'].set('Petugas uji')
                form.values['quantity'].set(str(original['stock'] + 1))
                form.save_button.invoke()
                root.update()
                assert form.winfo_exists(), 'Excess quantity must leave the form open'
                assert saved_count(app) == 0
                assert batch(app, key)['stock'] == original['stock']

                form.values['quantity'].set('1')
                form.note_text.insert('1.0', 'Dikirim ke area servis pagi')
                root.update()
                assert str(original['stock'] - 1) in form.remaining.cget('text')
                assert form.save_button.cget('state') == 'normal'
                form.save_button.invoke()
                root.update()
                assert not form.winfo_exists(), 'Successful save must close the form'
                assert saved_count(app) == 1
                assert batch(app, key)['stock'] == original['stock'] - 1
                assert app.page == 'Data Barang'
                assert app.table.selected == key

                # Consume the remainder: retain the batch and history, exclude it
                # from active dashboard totals, and prevent another outgoing entry.
                app.stock_out_button.invoke()
                form = app.stock_out_window
                form.values['quantity'].set(str(original['stock'] - 1))
                form.values['officer'].set('Petugas uji')
                form.note_text.insert('1.0', 'Sisa barang dikirim siang')
                form.save_button.invoke()
                root.update()
                assert saved_count(app) == 2
                assert batch(app, key)['stock'] == 0
                assert len(app.inventory.list_batches()) == 50
                assert len(overview(app.db)['active']) == initial_active - 1
                assert app.stock_out_button.cget('state') == 'disabled'
                app.availability_filter.set('Stok habis')
                root.update()
                assert [row['id'] for row in app.table.rows] == [key]
                app.availability_filter.set('Ada stok')
                root.update()
                assert len(app.table.rows) == 49
                assert all(row['stock'] > 0 for row in app.table.rows)
                app.availability_filter.set('Semua stok')
                root.update()
                assert len(app.table.rows) == 50

                # Master edits must not rewrite the historical product identity.
                changed = dict(batch(app, key), material='MASTER-EDITED', description='Deskripsi sesudah keluar')
                app.inventory.update(key, changed)
                app.stock_history_button.invoke()
                history = app.stock_history_window
                root.update()
                history.query.set(key)
                history.refresh()
                root.update()
                assert len(history.rows) == 2
                text = select_history(history, root)
                assert original['material'] in text and original['description'] in text
                assert 'MASTER-EDITED' not in text
                assert 'Petugas uji' in text
                history.query.set('Dikirim ke area servis pagi')
                history.refresh()
                root.update()
                assert len(history.rows) == 1, 'History search must find notes'
                assert 'Dikirim ke area servis pagi' in select_history(history, root)
                history.query.set('NO-MATCH-STOCK-OUT')
                history.refresh()
                root.update()
                assert not history.rows
                assert not history.table.get_children()
                history.destroy()
                assert not callback_errors, callback_errors
            finally:
                app.close()

            root = tk.Tk()
            app = Application(root, database_path)
            try:
                assert batch(app, key)['stock'] == 0
                assert saved_count(app) == 2
                assert len(app.inventory.list_batches()) == 50
                app.show_stock_history(key)
                history = app.stock_history_window
                root.update()
                assert len(history.rows) == 2
                assert original['description'] in select_history(history, root)
            finally:
                app.close()

    print('Stock-out UI passed: validation, partial/full stock, retained batch, dashboard totals, immutable searchable history, restart and 96/120 DPI layouts')


class StockOutWorkflowTest(unittest.TestCase):
    def test_stock_out_and_history(self):
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    run_workflow()
