# Panduan Pengembang Warehouse Check / SPARK

> Salinan untuk repository GitHub. Setup dan data demo repository dijelaskan pada [README](../README.md); path executable/.build dalam dokumen ini mengacu pada workspace asal.

**Serah terima dokumentasi — 5 Oktober 2026.** Acuan: kode proyek saat ini, executable **1.0.1** (rilis 4 Oktober 2026), dan SQLite **schema 7**. Panduan ini membantu pengembang menjalankan, memahami, menguji, dan melanjutkan aplikasi.

## 1. Urutan membaca

| Urutan | Dokumen | Isi |
|---|---|---|
| 1 | Panduan ini | Lingkungan, struktur folder, contoh service, pengujian, build, pembaruan, dan troubleshooting |
| 2 | [Arsitektur](../ARCHITECTURE.md) | Komponen, peta modul, alur fitur, dan batas tanggung jawab |
| 3 | [Data dan Aturan Bisnis](DATA_DAN_ATURAN_BISNIS.md) | Tabel, ID batch, alamat, aging, snapshot, migrasi, impor, dan transaksi stok |
| 4 | [Sistem Rekomendasi](SISTEM_REKOMENDASI.md) | Input, formula Site/Customer, ranking, keputusan, dan riwayat |
| 5 | [Antarmuka dan Kamera](ANTARMUKA_DAN_KAMERA.md) | Navigasi, tabel/scroll, denah, timer, thread, Live, dan scanner |

[README](../README.md) berisi setup dan ringkasan penggunaan repository ini. Dokumen berikut menjelaskan implementasi aplikasi versi 1.0.1.

Aplikasi adalah desktop lokal dengan mesin rekomendasi berbasis aturan dan konteks simulasi. Live membaca QR untuk tampilan sementara. Sesi Pengecekan menyimpan hasil dan keputusan. Database source Python dan database executable adalah dua file terpisah.

## 2. Teknologi

| Komponen | Peran |
|---|---|
| Python | Aturan bisnis, akses data, UI, worker, dan build |
| Tkinter/ttk + Tcl/Tk | Jendela, form, navigasi, tabel, scroll, callback |
| SQLite (`sqlite3`, bawaan Python) | Master, sesi, keputusan, riwayat stok, metadata; tanpa server terpisah |
| OpenCV + NumPy | Capture frame, deteksi/decode QR, pemrosesan frame |
| Pillow | Aset, label, frame yang ditampilkan di Tk |
| qrcode | Pembuatan QR dari ID batch |
| openpyxl | Impor/ekspor Excel; program tidak membutuhkan Microsoft Excel |
| ReportLab | Membuat laporan PDF |
| pypdfium2 | Render PDF untuk preview |
| PyInstaller | Paket executable Windows portable |
| unittest | Tes service, regresi, UI, dan packaging |

Rilis terakhir diuji pada **Windows x64, Python 3.14.4, PyInstaller 6.22.3, OpenCV 5.0.0**. Lock lengkap ada di [requirements-windows.lock.txt](../packaging/requirements-windows.lock.txt). [requirements.txt](../requirements.txt) berisi batas minimum runtime. Platform/versi lain belum tercakup dalam bukti rilis ini.

## 3. Menjalankan kode

Jalankan perintah PowerShell dari folder yang berisi `warehouse_app.py`. Pada komputer proyek:

```powershell
Set-Location -LiteralPath 'E:\Faiz\United Tractor\Warehouse\Baru'
$projectPython = '.\.build\venv\Scripts\python.exe'
& $projectPython --version
& $projectPython -m pip check
```

Lingkungan proyek pernah tidak menemukan Tcl/Tk otomatis. Bila muncul `Can't find a usable init.tcl`, atur salinan runtime yang tersedia dalam paket untuk proses PowerShell saat ini:

```powershell
$env:TCL_LIBRARY = (Resolve-Path '.\Aplikasi_Warehouse_Check_Rekomendasi_Final\_internal\_tcl_data').Path
$env:TK_LIBRARY = (Resolve-Path '.\Aplikasi_Warehouse_Check_Rekomendasi_Final\_internal\_tk_data').Path
& $projectPython -c "import tkinter as tk; r=tk.Tk(); r.withdraw(); r.destroy(); print('Tk OK')"
& $projectPython .\warehouse_app.py
```

Jika kedua direktori tidak ada, gunakan instalasi Python Windows yang menyertakan Tcl/Tk dan buat ulang venv. Jangan mencampur Tcl/Tk dari versi Python berbeda.

Startup source membuka `data/warehouse_demo.db`, dapat memigrasikan DB dengan backup, dan mengisi seed pada DB baru. Untuk eksperimen gunakan DB sementara pada bagian 5.

### Komputer pengembang baru

Dengan Python Windows x64 yang menyertakan Tcl/Tk:

```powershell
py -3.14 -m venv .venv
$projectPython = '.\.venv\Scripts\python.exe'
& $projectPython -m pip install -r .\packaging\requirements-windows.lock.txt
& $projectPython -m pip check
& $projectPython -c "import tkinter as tk; r=tk.Tk(); r.withdraw(); r.destroy(); print('Tk OK')"
& $projectPython .\warehouse_app.py
```

Interpreter dipanggil langsung sehingga `Activate.ps1` tidak wajib. Lock mencakup dependensi build. Venv adalah lingkungan mesin lokal; buat ulang di komputer tujuan. Source Python memerlukan runtime tersebut, sementara pengguna paket executable tidak perlu memasang Python/SQLite.

## 4. Folder dan jenis data

```text
warehouse_app.py            Entry point desktop / verifikasi paket
warehouse/                  Service, aturan, UI, kamera, laporan
assets/warehouse/           Aset visual
packaging/                  Ikon, versi Windows, lock, petunjuk paket
scripts/                    Generator data uji dan build
test_*.py                   Tes di root
tests/                      Tes tambahan
data/warehouse_demo.db     DB source Python
data_uji/                  Seed, workbook, manifest generator
Aplikasi_Warehouse_Check_Rekomendasi_Final/
   WarehouseCheck.exe       Program bundled
   _internal/               Runtime/aset bundled
   data/warehouse_demo.db   DB paket executable
   Data_Uji_Warehouse.xlsx  Workbook pengguna paket
   manifest_paket.json      Bukti build/verifikasi
docs/                      Dokumentasi dan bukti verifikasi
outputs/                   Presentasi, manual, gambar
arsip/                     Prototipe, data lama, cadangan
.build/                    Venv, staging, cache build
```

| Jenis data | Perbedaan |
|---|---|
| `seed_demo()` minimal | 50 batch, 6 rak, 162 lokasi; hanya pada DB tanpa metadata `seed_date` |
| DB source | Bisa sudah berisi perubahan pengguna; jumlah tidak dijadikan patokan tetap |
| `data_uji/warehouse_demo_seed.db` | Fixture 200 batch, 12 rak, 324 lokasi, skenario tambahan, dan satu sesi buatan PETUGAS-SIMULASI untuk tes; tanpa riwayat pengguna lama |
| DB awal paket 1.0.1 | 200 batch, 324 lokasi, konteks Site/Customer; 0 sesi/hasil/keputusan/penyelesaian |

Migrasi DB lama membuat tabel kebutuhan tetapi tidak mengisi skenario Site/Customer. Skenario berasal dari generator. Karena itu source dan paket dapat menunjukkan rekomendasi berbeda bila konteksnya berbeda.

`runtime_paths.py` menentukan data mengikuti folder executable untuk frozen app, bukan working directory. `outputs/` bukan dependency program. Generator masih membutuhkan `inventory_dummy.xlsx` dan `warehouse.db` dari root atau `arsip/pengembangan_lama/`; pertahankan sumber itu sampai ketergantungan generator diganti.

## 5. Contoh service tanpa menyentuh data pengguna

Simpan contoh berikut sebagai `contoh_service.py` di root, lalu jalankan `& $projectPython .\contoh_service.py`. Semua perubahan berada dalam direktori sementara. Kamera tidak dibuka.

```python
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from warehouse.database import connect
from warehouse.locations import Locations
from warehouse.inventory import Inventory
from warehouse.labels import payload
from warehouse.sessions import Sessions
from warehouse.reports import report_data

with TemporaryDirectory() as folder:
    db = connect(Path(folder) / 'uji.db')
    try:
        Locations(db).create_rack('A', 'B01')
        key = Inventory(db).add({
            'material': 'MAT-UJI', 'description': 'Barang contoh pengembang',
            'plant': 'BHT', 'storage_location': 'PBHT',
            'location_code': 'A-B01-K01-R01-T01',
            'received_date': date.today().isoformat(), 'stock': 5,
        })
        sessions = Sessions(db)
        session_id = sessions.start('Pengembang Uji', 'A')
        assert sessions.add_code(session_id, payload(key)) == (key, True)
        assert sessions.add_code(session_id, payload(key)) == (key, False)
        sessions.save_note(session_id, 'Catatan uji', key)
        sessions.finish(session_id)
        result = report_data(db, session_id)
        assert len(result['rows']) == 1
        assert result['session']['status'] == 'Selesai'
        print('Alur service OK:', result['counts'])
    finally:
        db.close()
```

`connect()` membuat schema; contoh tidak memanggil `seed_demo()`. UI dengan salinan data dapat dibuat melalui `Application(root, database_path)`. Tes `test_*_ui.py` memperlihatkan penggunaan DB sementara tersebut.

## 6. Pengujian

```powershell
& $projectPython -m unittest discover -s . -p 'test_*.py'
& $projectPython -m unittest discover -s tests -p 'test_*.py'
```

Jalankan dua discovery. Beberapa file UI memeriksa tampilan saat diimpor, dapat membuka jendela, dan memerlukan sesi desktop/Tcl; seluruh suite bukan tes headless.

Pada **rilis 4 Oktober 2026**, **129 + 19 = 148 tes lulus**. Angka itu bukti bertanggal, bukan jaminan untuk perubahan berikutnya. Lihat catatan pembaruan executable (`exe_update_20261004.json`; referensi workspace asal).

| Perubahan | Referensi tes di root, kecuali awalan `tests/` |
|---|---|
| Domain/schema/master | `test_foundation.py`, `test_locations.py`, `test_inventory.py`, `tests/test_recommendation_data.py` |
| Excel/QR | `test_inventory_excel.py`, `test_labels.py`, `test_labels_ui.py` |
| Sesi/penguncian | `test_sessions.py`, `test_stages67_ui.py` |
| Aturan/keputusan rekomendasi | `test_recommendations.py`, `test_recommendation_context.py`, `test_recommendation_history.py`, `test_recommendation_ui.py` |
| Tampilan/ekspor rekomendasi | `test_recommendation_surfaces.py`, `test_recommendation_reports.py`, `test_session_recommendation_display.py`, `tests/test_recommendation_views.py` |
| Kamera/Live | `test_live_monitor.py`, `test_live_camera_handoff.py`, `test_live_ui.py`, `test_camera_reports.py` |
| Dashboard/peta | `test_dashboard.py`, `test_dashboard_activity.py`, `test_dashboard_ui.py`, `test_dashboard_recommendation_ui.py` |
| Stok/tabel | `test_stock_movements.py`, `test_stock_out_ui.py`, `test_table_navigation_ui.py`, `test_inventory_ui.py` |
| Paket/dataset | `test_package_build.py`, `tests/test_runtime_paths.py`, `tests/test_trial_data.py` |

Gunakan DB sementara dan tanggal fixture eksplisit untuk kasus batas 30/31/90/91 hari. Tes regresi harus membuktikan perilaku, misalnya snapshot tetap setelah edit master, scan ulang tidak menggandakan hasil, atau Live melepaskan kamera sebelum scanner mengambilnya.

Ukuran tes desktop mencakup 1366×768/1920×1080 dan skala Tk 96/120 DPI. Kamera, beberapa label fisik, printer, dan DPI Windows aktual perlu uji perangkat. Dua QR sintetis tidak membuktikan jarak baca lapangan.

## 7. Data uji dan build Windows

Generator tidak perlu dijalankan setiap build. Untuk mencoba regenerasi tanpa mengganti hasil yang ada:

```powershell
& $projectPython .\scripts\create_trial_data.py --output-dir .\.build\data_uji_baru
```

`--today YYYY-MM-DD` dapat diberikan. Tanggal tidak boleh di masa depan atau mendahului penerimaan sumber. Generator membaca sumber, bekerja pada salinan, memeriksa integritas/impor/hash sumber, lalu mengganti hasil di tujuan. Output baru tidak otomatis dipakai builder; build selalu membaca `data_uji/warehouse_demo_seed.db` dan `data_uji/manifest.json`.

Workbook generator memiliki provenance/riwayat tambahan. Workbook paket dibentuk ulang menjadi Inventory, Lokasi, Petunjuk, Demand_Site_Simulasi, Kecocokan_Unit, Customer_Simulasi. Hanya Inventory dibaca saat impor. Mengedit sheet simulasi tidak mengubah rekomendasi aplikasi.

### Proses rilis

1. Jalankan tes relevan dan discovery penuh.
2. Naikkan angka serta string versi pada [version_info.txt](../packaging/version_info.txt); perbarui [MULAI_DI_SINI.txt](../packaging/MULAI_DI_SINI.txt).
3. Pastikan seed/manifest tersedia dan Tk dapat membuat jendela.
4. Pilih output yang belum ada:

```powershell
& $projectPython .\scripts\build_windows.py --output Aplikasi_Warehouse_Check_Rilis_Baru
```

Builder hanya berjalan di Windows. Ia membuat staging `.build/package_<waktu>`, membundel `--onedir --windowed`, menyertakan aset/runtime PDF, membuat DB demo bersih/workbook, dan menjalankan executable dengan `--verify-package`. Setelah lolos, folder disalin ke output dan manifest ditulis. Output yang sudah ada ditolak untuk melindungi DB pengguna.

Paket 1.0.1 berukuran sekitar 199 MB. Pindahkan seluruh folder termasuk `_internal` dan `data`. Mengedit source tidak memperbarui executable tanpa build ulang.

### Verifikasi paket bersih

Contoh untuk output baru yang belum digunakan:

```powershell
$release = (Resolve-Path '.\Aplikasi_Warehouse_Check_Rilis_Baru').Path
$report = Join-Path (Resolve-Path '.\docs').Path 'verifikasi_rilis_baru.json'
$process = Start-Process -FilePath (Join-Path $release 'WarehouseCheck.exe') -ArgumentList @('--verify-package', ('"' + $report + '"')) -WorkingDirectory (Resolve-Path '.\docs').Path -WindowStyle Hidden -Wait -PassThru
$process.ExitCode
Get-Content -LiteralPath $report -Raw
```

Sukses memerlukan exit 0 dan JSON `ok: true`. Pemeriksa memakai salinan DB sementara, membuka sembilan halaman/dialog, serta menguji impor/duplikasi, dua QR sintetis, keputusan, PDF, stok dan persistence. Kamera fisik tidak dinyalakan.

Mode frozen mensyaratkan **200 batch dan riwayat kosong**. Jangan menjalankannya sebagai health check umum pada DB pengguna yang sudah dipakai. Jika jumlah data rilis berubah, evaluasi asumsi 200 pada builder/manifest, `package_check.py`, dan tes dataset.

## 8. Pembaruan dengan data pengguna

1. Tutup aplikasi dan pastikan proses/perangkat selesai. Cadangkan seluruh folder paket lama.
2. Build dan verifikasi paket bersih di folder baru.
3. Untuk instalasi yang telah dipakai, buat kandidat dari program baru dengan **salinan DB pengguna**, bukan seed demo. Pertahankan backup DB dan berkas pengguna yang diperlukan.
4. Uji migrasi melalui `connect()` pada salinan; bandingkan isi master/riwayat penting, integritas, foreign key, dan versi. Uji UI melalui `Application(root, database_path)` pada salinan tersebut; pemeriksa paket bersih tidak cocok untuk riwayat aktif.
5. Setelah lulus dan sumber pengguna tidak berubah lagi, tempatkan kandidat pada jalur yang biasa dibuka. Runtime `_internal` harus sesuai executable baru.
6. Jika gagal, pulihkan paket dan DB backup yang berpasangan. Executable lama menolak DB dengan schema lebih baru; jangan menurunkan `user_version` manual.

Rilis 1.0.1 pada mesin ini memakai seed baru karena hash DB paket lama terbukti identik dengan data awal dan tanpa aktivitas pengguna. Ini pengecualian terverifikasi, bukan aturan umum pembaruan. Backup berada di `arsip/aplikasi_sebelum_update_20261004_183120/`; bukti ada pada catatan pembaruan (`exe_update_20261004.json`; referensi workspace asal).

Migrasi tidak mengisi skenario kebutuhan. Pemuatan konteks baru bagi pengguna lama harus terpisah dari penggantian master/riwayat.

## 9. Troubleshooting

| Gejala | Pemeriksaan pertama |
|---|---|
| `init.tcl` tidak ditemukan | Interpreter, instalasi Tcl/Tk, dan konfigurasi proses bagian 3 |
| Source baru, executable masih lama | Jalur `.exe`, versi/hash manifest; build ulang |
| Data source dan paket berbeda | Dua file DB pada bagian 4; tidak ada sinkronisasi otomatis |
| Site/Customer tidak muncul | Pemetaan material/unit, kebutuhan, threshold aturan, stok, tanggal; migrasi saja tidak mengisi konteks |
| Status hari ini berbeda dari laporan | Snapshot/batas sesi dibanding tanggal sekarang/batas default |
| Scan ulang tidak menambah baris | Deduplikasi batch per sesi; payload sama berarti batch sama |
| Kamera gagal/putus | Izin Windows, aplikasi lain, indeks, error worker, serah terima Live/scanner |
| Banyak QR hanya sebagian terbaca | Ukuran/fokus/cahaya/cetakan/resolusi; tidak ada jumlah atau jarak baca tetap |
| Excel ditolak | Template dan error per baris; cek lokasi, tanggal, stok, duplikat ID |
| Database versi lebih baru | Gunakan build sesuai schema; jangan mengubah versi DB manual |
| `database is locked` | Proses lain; gunakan salinan untuk eksperimen/tes |
| Aset/PDF gagal setelah pindah | Keutuhan `_internal`, `resource_root()`, dependency PDF dan font fallback |

Catat langkah reproduksi, halaman, pesan error, ukuran/skala layar, versi, dan source/paket yang dipakai. Reproduksi pada salinan DB. Startup belum memiliki logging terpusat; pesan error dan traceback tes membantu penelusuran.

## 10. Pedoman melanjutkan proyek

- Mulai dari service pada [peta modul](../ARCHITECTURE.md). Form, impor, dan scan memakai aturan yang sama.
- Bedakan material, batch, alamat, status umur, kondisi fisik, keputusan, dan status tindakan.
- Tambahkan perubahan schema sebagai migrasi versi berikutnya; uji DB lama dan pertahankan snapshot/trigger.
- Capture/decode/baca file yang lambat berjalan di worker. Widget serta koneksi SQLite aplikasi tetap di thread UI.
- Perubahan QR perlu kompatibilitas label lama; perubahan peta perlu menjaga klik dan arti K/R/T.
- Perubahan rekomendasi perlu tes ranking/alasan, kebutuhan kosong, syarat Layak, target berubah, revisi Draft, dan histori selesai.
- Belum ada adapter/API integrasi; bila ditambahkan, pertahankan batas service/konteks dan dokumentasikan kontraknya.
- Setiap rilis memperbarui versi, dokumentasi, data uji relevan, dan bukti pemeriksaan.

Batas implementasi saat ini: keputusan langsung dari Dashboard/Data Barang belum tersedia, serta belum ada login/role, RTSP/multi-kamera, sinkronisasi perusahaan, prediksi demand dari histori, denah ukuran fisik, atau ledger semua jenis perubahan stok. Detail batas masing-masing ada pada dokumen pendamping.

## 11. Verifikasi dokumentasi

Pada 5 Oktober 2026, 133 tautan lokal diperiksa tanpa tautan rusak; delapan blok perintah PowerShell lolos pemeriksaan sintaks. Contoh service pada bagian 5 dijalankan berhasil menggunakan DB sementara. Hash kedua DB aktif dan executable tetap identik sebelum/sesudah pemeriksaan. Bukti: verifikasi dokumentasi (`verifikasi_dokumentasi_20261005.json`; referensi workspace asal). Pemeriksaan ini memvalidasi dokumentasi, tidak menggantikan tes aplikasi ketika kode berubah.
