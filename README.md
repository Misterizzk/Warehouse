# Warehouse Check / SPARK

Aplikasi desktop untuk memantau umur barang, mencari lokasi rak, membuat QR, mencatat pengecekan dan keputusan petugas, serta mengekspor laporan. Folder ini adalah source aplikasi terbaru versi 1.0.1 dengan SQLite schema 7, disiapkan untuk GitHub pada 8 Oktober 2026.

## Menjalankan source di Windows

Gunakan Python Windows yang menyertakan Tkinter. Lingkungan verifikasi proyek memakai Python 3.14. Python, Git, dan SQLite memiliki peran berbeda: Git mengunggah source; Python menjalankan source; SQLite dibawa oleh Python.

Jalankan CMD dari folder repository:

```cmd
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts\prepare_demo.py
.venv\Scripts\python.exe warehouse_app.py
```

`prepare_demo.py` membuat database runtime dengan **200 batch, 12 rak, 324 lokasi**, serta skenario rekomendasi Site/Customer A/B/C. Riwayat petugas dimulai kosong. Jika database runtime sudah tersedia, perintah ini mempertahankannya. Jika aplikasi langsung dijalankan tanpa persiapan tersebut, seed dasar aplikasi hanya menghasilkan 50 batch dan tidak mencakup seluruh skenario kebutuhan rekomendasi.

Data runtime tersimpan di `data/warehouse_demo.db`. Folder `data/` tidak ikut di-push. Tanggal barang pada dataset adalah snapshot; status umur tetap mengikuti tanggal komputer.

## Fitur yang tersedia

- Dashboard: statistik aging, prioritas, peta section dan detail kolom/baris/tingkat rak.
- Data Barang: input/edit, pencarian/filter, lokasi, QR/label, serta impor/ekspor Excel.
- Pengecekan: sesi Draft, ID manual atau scan QR, catatan, dan snapshot hasil.
- Rekomendasi: aturan aging dengan kebutuhan Site dan kecocokan Customer simulasi; keputusan tetap dibuat petugas.
- Laporan: riwayat/detail, ekspor Excel dan PDF, serta tindak lanjut.
- Live: monitoring QR sementara tanpa membuat hasil pengecekan otomatis.
- Barang keluar: pengurangan stok disertai riwayat transaksi.

Rekomendasi belum merupakan AI yang telah dilatih. Marking area penerimaan dan deteksi penumpukan masih merupakan usulan, belum diimplementasikan pada source ini.

## Data uji dan privasi

[data_uji/Data_Uji_Warehouse.xlsx](data_uji/Data_Uji_Warehouse.xlsx) berisi enam sheet: Inventory, Lokasi, Petunjuk, Demand_Site_Simulasi, Kecocokan_Unit, dan Customer_Simulasi. Workbook tidak memuat riwayat petugas lama. Hanya sheet Inventory dibaca oleh impor aplikasi; sheet kebutuhan rekomendasi merupakan referensi data simulasi.

`data_uji/warehouse_demo_seed.db` adalah fixture contoh yang sengaja disertakan di Git. Fixture berisi satu sesi buatan bernama PETUGAS-SIMULASI untuk menguji pembersihan riwayat oleh proses instalasi. `prepare_demo.py` dan build Windows menyalin master dari fixture tersebut dan menghasilkan database pengguna dengan nol sesi/hasil/keputusan. Jangan mengganti fixture dengan database operasional pengguna.

Riwayat pengguna dari proyek asal, database executable, arsip, lingkungan Python, cache, serta hasil build tidak disertakan.

## Dokumentasi

- [Dokumentasi kode dan sintaks (PDF)](outputs/Warehouse_Check_Dokumentasi_Kode_Pengembang.pdf)
- [Arsitektur](ARCHITECTURE.md)
- [Panduan pengembang](docs/PANDUAN_PENGEMBANG.md)
- [Data dan aturan bisnis](docs/DATA_DAN_ATURAN_BISNIS.md)
- [Rekomendasi dan keputusan](docs/SISTEM_REKOMENDASI.md)
- [Antarmuka dan kamera](docs/ANTARMUKA_DAN_KAMERA.md)

Dokumen rinci/PDF disusun dari workspace asal pada 5 Oktober 2026. Path `.build/venv` dan folder executable yang disebut di sana adalah konteks workspace tersebut; untuk repository ini ikuti setup dalam README. Bukti verifikasi lokal lama tidak ikut diunggah.

## Pengujian

```cmd
.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py"
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Tes UI memerlukan Tkinter dan sesi desktop. Kamera dan printer fisik memerlukan pengujian perangkat terpisah.

## Membuat paket Windows

```cmd
.venv\Scripts\python.exe -m pip install -r packaging\requirements-windows.lock.txt
.venv\Scripts\python.exe scripts\build_windows.py --output Aplikasi_Warehouse_Check_Baru
```

Folder output harus belum ada. Script menggunakan fixture `data_uji` dan membuat instalasi dengan riwayat kosong. Paket executable hasil build tidak ikut masuk repository.

`scripts/create_trial_data.py` adalah generator migrasi dataset dari workspace lama; ia memerlukan database sumber serta dua file legacy yang tidak disertakan dalam repository ini. Untuk memakai demo yang tersedia gunakan `prepare_demo.py`, bukan generator legacy tersebut.
