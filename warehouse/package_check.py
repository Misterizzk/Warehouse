"""Non-destructive smoke check executed by both Python and a frozen release."""
import json
import sqlite3
import sys
import tempfile
import traceback
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from .runtime_paths import application_root, database_path, resource_root


def _readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)


def verify_package(report_path):
    report = {'ok': False, 'frozen': bool(getattr(sys, 'frozen', False)),
              'checked_at': datetime.now().astimezone().isoformat(),
              'application_root': str(application_root()),
              'resource_root': str(resource_root()),
              'default_database': str(database_path()), 'checks': {}}
    target = Path(report_path).resolve()
    root = app = db = fresh = temporary_context = None
    try:
        import tkinter as tk
        import cv2
        import numpy as np
        import pypdfium2 as pdfium
        from PIL import Image
        from .database import connect
        from .inventory_excel import read_inventory, preview, commit_import
        from .labels import qr_image, label_image, resolve, payload
        from .camera import decode_frame
        from .sessions import Sessions
        from .recommendations import RecommendationService, recommend_for
        from .stock_movements import StockMovements
        from .reports import report_data, export_excel, export_pdf
        from .ui import Application
        from .label_ui import LabelPreview
        from .report_ui import PDFPreview

        default = database_path()
        if not default.is_file():
            raise FileNotFoundError(f'Database paket tidak ditemukan: {default}')
        with closing(_readonly(default)) as source_db:
            report['default_database_batches'] = source_db.execute('SELECT COUNT(*) FROM batches').fetchone()[0]
        selected = default
        if not report['frozen']:
            enriched = application_root() / 'data_uji' / 'warehouse_demo_seed.db'
            if enriched.is_file():
                selected = enriched
        workbook = application_root() / 'Data_Uji_Warehouse.xlsx'
        if not workbook.is_file():
            workbook = application_root() / 'data_uji' / 'Data_Uji_Warehouse.xlsx'
        report.update(verified_database=str(selected), workbook=str(workbook))
        report['versions'] = {'python': sys.version.split()[0], 'opencv': cv2.__version__}
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_context = tempfile.TemporaryDirectory(prefix='warehouse_package_check_', ignore_cleanup_errors=True)
        with temporary_context as temporary:
            folder = Path(temporary)
            copy_path = folder / 'test.db'
            with closing(_readonly(selected)) as source_db, closing(sqlite3.connect(copy_path)) as destination:
                source_db.backup(destination)
            db = connect(copy_path)
            report['counts'] = {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                                for table in ('batches', 'locations', 'check_sessions', 'check_results',
                                              'recommendation_decisions', 'recommendation_completions')}
            assert report['counts']['batches'] == 200, report['counts']
            if report['frozen']:
                assert all(report['counts'][table] == 0 for table in
                           ('check_sessions', 'check_results', 'recommendation_decisions',
                            'recommendation_completions')), report['counts']
                report['checks']['clean_first_run'] = True
            for name in ('rack_3x3_dark.png', 'carton_blank_label.png'):
                path = resource_root() / 'assets' / 'warehouse' / name
                with Image.open(path) as asset:
                    asset.load()
                    assert asset.width > 0 and asset.height > 0
            report['checks']['assets'] = True

            rows = read_inventory(workbook)
            assert len(rows) == 200, len(rows)
            duplicates = preview(db, rows)
            assert len(duplicates) == 200 and all(any('duplikat' in error.lower() for error in row['errors']) for row in duplicates)
            fresh = connect(folder / 'import.db')
            with fresh:
                fresh.executemany('INSERT INTO locations(code,area,rack,"column","row",level) VALUES(?,?,?,?,?,?)',
                                  [tuple(row) for row in db.execute('SELECT code,area,rack,"column","row",level FROM locations')])
            validation = preview(fresh, rows)
            assert all(not row['errors'] for row in validation), [row for row in validation if row['errors']][:3]
            imported = commit_import(fresh, rows)
            assert len(imported) == 200
            fresh.close()
            fresh = None
            report['checks']['excel_import'] = {'rows': 200, 'duplicate_ids_rejected': 200, 'fresh_import': 200}

            identifiers = [row[0] for row in db.execute('SELECT id FROM batches WHERE stock>0 ORDER BY id LIMIT 2')]
            assert len(identifiers) == 2
            first = resolve(db, payload(identifiers[0]))
            images = [qr_image(key).resize((400, 400), Image.Resampling.NEAREST) for key in identifiers]
            canvas = Image.new('RGB', (1100, 650), 'white')
            canvas.paste(images[0], (60, 100))
            canvas.paste(images[1], (640, 100))
            found = decode_frame(cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2BGR))
            assert {code for code, _ in found} == {payload(key) for key in identifiers}, [code for code, _ in found]
            label_image(first).save(folder / 'label.png')
            report['checks']['qr_label'] = {'synthetic_qrs_decoded': len(found), 'physical_camera_tested': False}

            sessions = Sessions(db)
            session_id = sessions.start('Verifikasi paket', 'Area uji')
            assert sessions.add_code(session_id, payload(identifiers[0])) == (identifiers[0], True)
            assert sessions.add_code(session_id, payload(identifiers[0])) == (identifiers[0], False)
            sessions.save_note(session_id, 'Catatan sesi uji')
            sessions.save_note(session_id, 'Catatan barang uji', identifiers[0])
            advice = recommend_for(first)
            assert advice['code'] != 'DATA_PERLU_DIPERBAIKI'
            recommendations = RecommendationService(db)
            decision = recommendations.save_decision(session_id, identifiers[0], 'Layak',
                                                      'Prioritaskan pemakaian', 'Barang layak untuk didahulukan.')
            sessions.finish(session_id)
            recommendations.complete(decision['id'], 'Verifikasi paket', 'Tindakan uji selesai.')
            assert recommendations.for_result(session_id, identifiers[0])['action_status'] == 'Selesai'
            report['checks']['recommendation_workflow'] = True
            try:
                sessions.save_note(session_id, 'Tidak boleh berubah')
            except ValueError:
                pass
            else:
                raise AssertionError('Sesi selesai belum terkunci')
            assert len(sessions.results(session_id)) == 1
            report['checks']['session_workflow'] = True
            data = report_data(db, session_id)
            export_excel(data, folder / 'report.xlsx')
            export_pdf(data, folder / 'report.pdf')
            document = pdfium.PdfDocument(folder / 'report.pdf')
            try:
                page = document[0]
                bitmap = page.render(scale=1)
                try:
                    image = bitmap.to_pil()
                    assert image.width > 0
                    image.save(folder / 'report-preview.png')
                finally:
                    bitmap.close()
                    page.close()
                report['checks']['report_export_pdf_render'] = {'pages': len(document)}
            finally:
                document.close()
            movement = StockMovements(db).issue(identifiers[0], 1, date.today().isoformat(), 'Verifikasi paket', 'Salinan sementara')
            expected_stock = first['stock'] - 1
            assert movement['stock_after'] == expected_stock
            db.close()
            db = connect(copy_path)
            assert resolve(db, payload(identifiers[0]))['stock'] == expected_stock
            assert StockMovements(db).get(movement['id'])['quantity'] == 1
            assert Sessions(db).get(session_id)['status'] == 'Selesai'
            assert Sessions(db).results(session_id)[0]['stock'] == first['stock']
            assert RecommendationService(db).latest_action_for_batch(identifiers[0])['action_status'] == 'Selesai'
            report['checks']['stock_and_reopen_persistence'] = True
            db.close()
            db = None

            callback_errors = []
            root = tk.Tk()
            root.withdraw()
            root.report_callback_exception = lambda kind, value, tb: callback_errors.append(''.join(traceback.format_exception(kind, value, tb)))
            app = Application(root, copy_path)
            visited = []
            for name in ('Dashboard', 'Pengecekan', 'Data Barang', 'Laporan', 'Live'):
                app.show(name)
                root.update()
                visited.append(name)
            app.show_locations()
            root.update()
            visited.append('Lokasi')
            app.show_excel()
            app.excel_window.withdraw()
            root.update()
            app.excel_window.destroy()
            visited.append('Impor/Ekspor')
            label = LabelPreview(app, identifiers[0])
            label.withdraw()
            root.update()
            label.destroy()
            pdf_window = PDFPreview(root, data)
            pdf_window.withdraw()
            root.update()
            pdf_window.destroy()
            assert not callback_errors, callback_errors
            app.close()
            app = root = None
            report['checks']['desktop_pages'] = visited + ['Label QR', 'Preview PDF']
            report['checks']['tk_callback_errors'] = callback_errors
            report['ok'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        for connection in (fresh, db):
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
        if app is not None:
            try:
                app.close()
                root = None
            except Exception:
                pass
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        if temporary_context is not None:
            temporary_context.cleanup()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1
