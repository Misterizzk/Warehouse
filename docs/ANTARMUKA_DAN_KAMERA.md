# Antarmuka desktop dan kamera

> Salinan untuk repository GitHub. Setup dan data demo repository dijelaskan pada [README](../README.md); path executable/.build dalam dokumen ini mengacu pada workspace asal.

Dokumen ini menjelaskan implementasi yang ada di kode, untuk pengembang yang akan mengubah UI atau alur kamera.
Semua tautan sumber relatif terhadap direktori `docs/`; nama metode menjadi titik pencarian di berkas tersebut.
Data aplikasi masih bersifat lokal/simulasi. Status umur bukan hasil penilaian kondisi fisik barang.

## 1. Titik masuk dan navigasi

- [warehouse_app.py](../warehouse_app.py) membuat `tk.Tk()`, membangun `Application`, lalu menjalankan `mainloop()`.
- Argumen `--verify-package <path>` menjalankan pemeriksaan paket melalui jalur khusus sebelum membuat jendela utama.
- [warehouse/ui.py](../warehouse/ui.py), kelas `Application`, memiliki koneksi database, objek `Inventory`, navigasi, timer, dan `LiveMonitor`.
- `Application.__init__()` memanggil `connect()` dan `seed_demo()`, lalu membuka Dashboard.
- Ukuran awal adalah `min(1440, lebar_layar-40)` × `min(900, tinggi_layar-70)`; ukuran minimum 800×520.
- Sidebar berisi Dashboard, Pengecekan, Data Barang, Laporan, dan Live. Klik indikator Live di header membuka halaman Live.
- `show(page)` menutup jendela kamera Pengecekan, menghancurkan widget dalam `body`, membaca ulang daftar batch, lalu membangun halaman tujuan.
- Pergantian halaman tidak membuat ulang `LiveMonitor`; pemantauan Live dimiliki `Application`, bukan widget halaman.
- `show_locations()` membuka subhalaman Lokasi dan tetap menandai navigasi Data Barang sebagai aktif.

| Tujuan perubahan | Sumber dan titik masuk |
|---|---|
| Header, sidebar, footer, warna dasar, navigasi, detail barang | [ui.py](../warehouse/ui.py): `Application.__init__`, `show`, `show_item` |
| Susunan Dashboard, metrik, prioritas, panel informasi, detail rak | [dashboard_ui.py](../warehouse/dashboard_ui.py): `DashboardPage` |
| Denah tampak atas, target klik, keyboard, tooltip | [rack_map.py](../warehouse/rack_map.py): `RackMap` |
| Tabel barang dan hasil pengecekan | [inventory_table.py](../warehouse/inventory_table.py): `InventoryTable` |
| Form tambah/edit batch | [batch_ui.py](../warehouse/batch_ui.py): `BatchEditor` |
| Master lokasi/rak | [location_ui.py](../warehouse/location_ui.py): `LocationPage` |
| Preview, validasi, tombol impor/ekspor | [excel_ui.py](../warehouse/excel_ui.py): `ExcelWindow` |
| Daftar sesi, input kode, catatan, saran dan keputusan | [session_ui.py](../warehouse/session_ui.py): `SessionPage` |
| Jendela scan yang dapat disimpan | [camera_ui.py](../warehouse/camera_ui.py): `CameraWindow` |
| Video Live, kartu QR, penghitung, kontrol kamera | [live_ui.py](../warehouse/live_ui.py): `LivePage` |
| Pengambilan frame, decoder, pemilihan backend | [camera.py](../warehouse/camera.py): `open_device`, `decode_frame`, `CameraWorker` |
| Konfirmasi berulang dan masa tahan QR Live | [live_monitor.py](../warehouse/live_monitor.py): `LiveMonitor` |
| Riwayat laporan, ekspor, preview PDF | [report_ui.py](../warehouse/report_ui.py): `ReportPage`, `PDFPreview` |
| Label QR, barang keluar, ikon | [label_ui.py](../warehouse/label_ui.py), [stock_ui.py](../warehouse/stock_ui.py), [visuals.py](../warehouse/visuals.py) |

## 2. Widget, gaya, dan pengguliran

UI menggunakan Tkinter/ttk. Tema `clam`, font Segoe UI, dan konstanta `BG`, `PANEL`, `FG`, `MUTED`, `BLUE` disiapkan di `ui.py`.
Style Treeview, heading, pilihan baris, scrollbar tanpa panah, serta Combobox readonly juga diatur di sana.
Sebagian komponen memiliki palet lokal: `inventory_table.COLORS`, `rack_map.STATUS`, `live_ui.INK/TINT`, dan `dashboard_ui.LABEL_COLORS`.
Perubahan warna status perlu diperiksa pada semua pemetaan ini; belum ada satu definisi tema yang mencakup seluruh komponen.

`InventoryTable` bukan `ttk.Treeview`: ia membangun baris dari Frame/Label di dalam Canvas agar badge status memiliki warna per sel.
Header memakai Canvas terpisah, digerakkan bersama scrollbar horizontal; scrollbar muncul jika isi melampaui area tampilan.
Lebar minimum kolom utama adalah 295/155/80/100/180 piksel. Mode `inspection=True` menambah waktu cek dan catatan.
Klik baris atau tombol Up/Down/Home/End memilih barang dan memanggil `on_select`; wheel terpasang hingga widget anak.
`move()` memeriksa apakah tabel masih ada setelah callback, karena pemilihan dapat menutup dialog dan berpindah halaman.
Tabel menampilkan stok nol sebagai `Stok habis` pada inventori, sedangkan hasil inspeksi mempertahankan status snapshot.
Ringkasan saran/tindakan tersedia melalui `recommendation_caption()`; detail panjang ada di drawer `show_item()`.

Dashboard memakai Canvas viewport dengan isi minimum lebar 940 piksel dan tinggi minimum yang dihitung dari kebutuhan panel.
`DashboardPage.layout()` menampilkan scrollbar horizontal/vertikal bila perlu; peta dan prioritas berada di kiri, panel pendukung di kanan.
Wheel halaman tidak dipasang ulang ke Treeview atau Scrollbar, sehingga gulir tabel tetap dapat bekerja sendiri.
Drawer Data Barang mempunyai scrollbar sendiri; tombol Catat barang keluar berada di luar isi drawer yang digulir.
Live memakai dua panel berbobot 7:4 dengan lebar minimum 420/315; daftar kanan bergulir tanpa menggerakkan video.
Tidak semua halaman memakai mekanisme responsive yang sama: jangan menganggap seluruh UI memiliki penataan ulang otomatis.

## 3. Peta tampak atas dan detail rak

Alamat lokasi mengikuti `AREA-RAK-Kxx-Rxx-Txx`, misalnya `A-B01-K03-R02-T01`.
Satu rak mempunyai 3 kolom × 3 baris × 3 tingkat = 27 alamat; validasi alamat berada di [domain.py](../warehouse/domain.py).
[dashboard.py](../warehouse/dashboard.py) menyediakan `overview()`, `aggregate()`, `aggregate_sections()`, dan `aggregate_columns()`.
Modul data tersebut menghitung proyeksi; `RackMap` hanya menggambar dan meneruskan pilihan pengguna.

1. Setiap sel lokasi merangkum batch pada satu alamat lengkap K/R/T.
2. Satu section tampak atas adalah pasangan `(column, row)` atau K/R, mengagregasi tiga tingkat T01–T03.
3. Setiap rak di peta memiliki sembilan target section, disusun K01–K03 mendatar dan R01–R03 menurun.
4. Klik section memanggil `pick_section(key, column, row)` dan membuka tampak samping satu kolom K yang dipilih.
5. Tampak samping memperlihatkan sembilan alamat: R01–R03 dari kiri ke kanan, T03–T01 dari atas ke bawah.
6. Baris R yang diklik disorot biru; tombol kolom sebelumnya/berikutnya memakai ulang jendela detail yang sama.
7. Klik alamat pada tampak samping membuka daftar batch lokasi; memilih batch membuka detail di Data Barang.

Warna agregat hanya ditentukan batch dengan stok > 0. Urutannya: Melewati batas > Warning > Data perlu diperbaiki > Normal.
Tanpa batch berstok, sel/section/kolom/rak berstatus `Tanpa stok`; batch stok nol tetap tersedia dalam data/detail.
Warna satu section bukan warna satu tingkat tertentu. Heading dan bingkai rak bukan target klik.
Peta menampilkan enam rak per halaman jika lebar Canvas ≥550 piksel, atau tiga rak jika lebih sempit.
Panah keyboard memindahkan section, Enter/Space membukanya; tooltip menyebut kolom, baris, status, jumlah batch, dan stok.
Resize peta ditunda 25 ms untuk menggabungkan pembaruan; tooltip muncul setelah 350 ms. `destroy()` membatalkan pekerjaan tersebut.

Gambar rak/karton dipakai dari `assets/warehouse/`; detail tetap menyediakan gambar geometri sederhana ketika aset tidak tersedia.
Aset rak dipakai untuk susunan tiga baris/tiga tingkat; seluruh tombol alamat tetap widget Tk yang dapat diklik.
Posisi dinding, lorong, dan ukuran peta bersifat skematis, bukan ukuran gudang atau koordinat hasil kamera.
`Sorot scan terakhir` memakai lokasi master batch saat ini; waktu/hasil pengecekannya tetap berasal dari snapshot historis.
Sorotan ini diminta lewat tombol, tidak otomatis diterapkan setiap kali Dashboard dibuka.
Klik section lain membersihkan sorotan scan. Membaca QR tidak membuktikan barang berada di alamat master tersebut.

## 4. Tanggal, status, dan pembaruan tampilan

Umur barang dihitung dari tanggal komputer dikurangi tanggal masuk melalui `domain.aging()`.
Dashboard, inventori, dan Live memakai batas default: Normal ≤30 hari, Warning ≤90 hari, Melewati batas >90 hari.
Sesi Pengecekan dapat memakai batas sendiri yang disimpan saat sesi dibuat; hasil yang sudah tercatat menyimpan umur/status saat cek.
Karena waktunya berbeda, warna inventori hari ini dapat berbeda dari hasil sesi lama untuk batch yang sama.

| Pemicu/callback | Interval/perilaku aktual |
|---|---|
| `Application.check_day()` | `after(30000, ...)`; memperbarui jam header setiap panggilan |
| Pergantian tanggal | `check_day()` membangun ulang halaman aktif, kecuali Lokasi dan Pengecekan |
| `DashboardPage.reload()` | Dipanggil saat halaman dibuat, tombol Perbarui data, filter area, atau sorotan scan |
| `Application.show()` | Membaca ulang inventori ketika navigasi dijalankan |
| `Application.poll_live()` | `after(120, ...)`; mengonsumsi frame/pesan dan mengubah indikator header |
| Detail QR Live | Lookup ketika himpunan kode berubah, atau setelah 3 detik selama masih ada kode |
| `CameraWindow.poll()` | `after(80, ...)`; pesan worker dan frame scan Pengecekan |
| Pembacaan Excel | Thread baca workbook; hasil antrean diperiksa melalui `after(80, ...)` |

Timer Tk adalah jadwal callback, bukan jaminan laju rendering atau interval presisi ketika UI sibuk.
Tidak ada polling Dashboard setiap 30 detik pada tanggal yang sama: gunakan Perbarui data untuk membaca ulang proyeksi.
Dialog detail rak/lokasi dibangun dari data saat dibuka; `reload()` Dashboard tidak membangun ulang semua dialog yang telah terbuka.
Lokasi dan Pengecekan dikecualikan dari pembangunan ulang harian; hasil sesi tetap snapshot, bukan umur yang terus bergerak.
Saran sesi Draft membaca inventori saat ini ketika dialog dibuat; saran historis memakai snapshot yang tersedia di hasil/keputusan.

## 5. Pemilik thread, kamera, dan koneksi database

`Application` membuat dan memakai koneksi SQLite pada thread UI. Widget Tk, lookup QR, validasi, serta transaksi service berjalan di thread ini.
`CameraWorker` memiliki thread daemon yang membuka perangkat, membaca frame, mendecode QR, dan melepaskan perangkat.
Worker tidak memegang koneksi SQLite dan tidak menyentuh widget; ia mengirim `(frame, found)` dan pesan melalui `queue.Queue`.
Antrean frame berkapasitas satu: frame lama dibuang sebelum frame terbaru dimasukkan. Antrean pesan dipisahkan dari antrean frame.
`DEVICE_LOCK` di `camera.py` mengizinkan satu worker kamera aplikasi memegang perangkat, termasuk ketika sedang mendeteksi indeks kamera.
Ini merupakan lock dalam satu proses; aplikasi kamera lain di Windows tetap dapat berebut perangkat.

`stop()` hanya menyetel Event; tidak menunggu thread selesai. `finally` worker melepaskan capture, lock, lalu mengirim `stopped`.
`LiveMonitor.is_running` tetap true selama pelepasan berlangsung sampai `poll()` memproses pesan `stopped`.
Worker lama yang masih hidup atau lock yang sedang dipegang membuat `start()` menolak pembukaan baru dengan pesan yang dapat ditampilkan UI.
Saat aplikasi ditutup, `Application.close()` menandai `closing`, menutup scanner, meminta Live berhenti, membatalkan timer, dan menutup DB/Tk.
Penutupan aplikasi tidak melakukan `join()` eksplisit pada thread kamera; cleanup driver bergantung penyelesaian worker daemon.

Impor Excel mengikuti batas serupa: hanya `read_inventory(path)` berjalan di thread latar.
`preview()` dan `commit_import()` memakai koneksi aplikasi di callback UI; pemilihan file saja tidak menyimpan batch.
Tombol simpan aktif setelah semua baris valid; `ExcelWindow.destroy()` membatalkan polling yang masih terjadwal.

## 6. Live: data sementara dan daftar stabil

`LiveMonitor` berada pada `Application`, sedangkan `LivePage` boleh dihancurkan/dibuat ulang ketika navigasi berubah.
Aktifkan kamera memilih indeks 0–4; kamera laptop biasanya indeks 0, tetapi urutan sebenarnya ditentukan driver/perangkat.
Indikator header menampilkan status aktif/jeda/nonaktif serta jumlah QR dan batch melewati batas dari snapshot Live.
Pergi ke Dashboard, Data Barang, Pengecekan tanpa membuka scanner, atau Laporan tidak menghentikan Live.
Klik Matikan kamera menghapus niat melanjutkan otomatis, lalu meminta worker berhenti.

- QR baru harus terbaca pada dua frame yang dikonsumsi `LiveMonitor.poll()` sebelum ditampilkan (`confirm_reads=2`).
- Dua label dengan isi identik dalam satu frame dihitung satu observasi, sehingga tidak langsung memenuhi konfirmasi.
- Pembacaan yang terlewat ditahan hingga 2 detik sejak `last_seen` (`hold_seconds=2.0`); batas `>=` menghapus track.
- Konfirmasi tidak harus pada dua frame berturut-turut jika track belum kedaluwarsa; setelah kedaluwarsa diperlukan konfirmasi baru.
- Kartu yang ditahan tetap dihitung dalam snapshot, tetapi kotak video tidak digambar jika QR tidak terlihat pada frame yang dikonsumsi.
- TTL tetap diperiksa ketika polling tidak menerima frame baru; berhenti mengosongkan track dan frame.
- Tidak ada batas keras jumlah QR/track atau riwayat deteksi permanen; jumlah praktis bergantung isi frame dan kemampuan decoder/perangkat.

`LivePage._update_list()` mempertahankan widget, urutan kartu yang masih ada, dan posisi gulir ketika daftar berubah.
QR yang baru datang diurutkan menurut prioritas status lalu waktu pertama terlihat dan kode; kartu lama tidak terus disortir ulang.
Perubahan sudut/posisi QR memperbarui overlay tanpa menulis ulang label kartu yang datanya tetap.
Signature kartu juga mencakup saran dan keputusan terakhir, sehingga perubahan tujuan rekomendasi dapat muncul tanpa scan ulang.
`current_item()` membaca inventori saat ini: QR tidak dikenal diberi penanda; stok ≤0 menjadi Stok habis dan saran dinonaktifkan.
Live tidak membuat sesi, hasil pengecekan, penanda scan terakhir, atau laporan. Saran/keputusan yang ditampilkan adalah hasil baca.
Istilah “Live tidak menyimpan” berlaku pada observasi Live, bukan berarti seluruh proses aplikasi membuka SQLite dalam mode read-only.
Startup tetap menjalankan `database.connect()` yang dapat membuat/migrasi skema dan `seed_demo()` yang dapat mengisi data awal bila diperlukan.

## 7. Scan Pengecekan dan serah terima kamera

Pengecekan manual dan kamera akhirnya memakai `Sessions.add_code()` di [sessions.py](../warehouse/sessions.py).
`SessionPage.open_camera()` menutup scanner sebelumnya, memanggil `pause_live_for_scan()`, lalu membuat `CameraWindow` untuk sesi Draft.
Jika Live aktif, aplikasi menyimpan niat melanjutkan dan meminta worker Live berhenti; membuka dialog saja belum mengaktifkan scanner.
Saat Aktifkan kamera atau Deteksi kamera dipilih, scanner menunggu `LiveMonitor.is_running` false dengan callback ulang 120 ms.
Setelah perangkat dilepas, scanner mulai capture/discovery. Lock tetap menjadi perlindungan terakhir terhadap pembukaan tumpang tindih.
Jika pembuatan jendela scanner gagal, `open_camera()` meminta Live dilanjutkan kembali.

Scanner menampilkan satu kandidat QR dan membekukan preview; banyak kode berbeda dalam satu frame meminta pengguna mendekatkan satu label.
Decode saja tidak menulis hasil. Tombol Simpan hasil scan memanggil `add_code()`, kemudian memperbarui tabel sesi.
Konfirmasi sukses juga menyimpan salinan frame terakhir di memori `Application.last_camera_frame`; frame ini tidak disimpan sebagai berkas oleh alur tersebut.
Dashboard menampilkan salinan itu dengan label “Hasil scan terakhir • kamera tidak aktif”; panel ini bukan stream Live.
QR tidak dikenal menonaktifkan penyimpanan; Scan barang berikutnya/Lewati hasil ini membuka kembali preview.
Batch yang sama dalam sesi tidak menambah hasil atau mengganti snapshot/waktu cek pertama, tetapi konfirmasi ulang memperbarui metadata `last_check`.
Sesi yang selesai menolak tambahan hasil; catatan dan keputusan mengikuti aturan penguncian service masing-masing.

`CameraWindow.destroy()` membatalkan polling/start tertunda, meminta worker scanner berhenti, lalu memanggil `resume_live_after_scan(worker)`.
Live baru dimulai lagi setelah monitor lama tidak aktif dan thread scanner tidak hidup; pemeriksaan dilakukan melalui polling aplikasi.
Indeks Live sebelumnya dipakai kembali. Membuka scanner berikutnya membatalkan permintaan resume lama yang belum dijalankan.
Live yang sengaja dimatikan pengguna tidak otomatis dihidupkan setelah scanner ditutup.
Tombol Hentikan kamera pada scanner menghentikan capture tetapi tetap membiarkan dialog terbuka; resume Live diminta saat dialog ditutup.

## 8. Sumber kamera, performa, dan fallback aktual

`open_device()` mencoba backend Windows DirectShow → Media Foundation → backend otomatis; non-Windows mencoba backend otomatis.
Setiap percobaan harus berhasil membuka perangkat dan membaca frame pertama; capture gagal dilepas sebelum mencoba backend berikutnya.
Capture meminta ukuran 1280×720 dan FPS 15, lalu loop menunggu 0,06 detik setelah decode sebelum membaca lagi.
Nilai tersebut adalah permintaan/target, bukan hasil benchmark atau jaminan FPS; driver, decode, dan polling UI turut membatasi laju efektif.
`decode_frame()` mengecilkan sisi terpanjang ke maksimum 1280 piksel, mencoba `detectAndDecodeMulti()`, lalu decoder tunggal bila belum ada hasil.
Koordinat sudut dikembalikan ke skala frame asli; UI menyesuaikannya ke video yang diperkecil tanpa memperbesar melebihi ukuran sumber.
Discovery memeriksa indeks 0–4 secara berurutan. Tidak ada field URL RTSP, konfigurasi CCTV jaringan, autentikasi kamera, atau multi-kamera simultan.
Kegagalan membuka kamera memberi pesan izin/perangkat/aplikasi lain; koneksi terputus meminta pengguna mengaktifkan kamera kembali.
Tidak ada reconnect otomatis atau pengalihan otomatis ke kamera fisik lain. Pengguna dapat memilih indeks berbeda atau memasukkan kode manual di Pengecekan.
Status QR mengikuti ID batch yang disimpan, bukan object detection, identifikasi kondisi kemasan, atau penentuan koordinat fisik.

## 9. Verifikasi dan checklist manual

Tes yang menjadi referensi perilaku: [test_live_monitor.py](../test_live_monitor.py), [test_live_camera_handoff.py](../test_live_camera_handoff.py), dan [test_live_ui.py](../test_live_ui.py).
[test_camera_reports.py](../test_camera_reports.py) mendecode satu/dua QR sintetis dan menguji cleanup capture tiruan; [test_stages89_ui.py](../test_stages89_ui.py) menguji konfirmasi tanpa webcam fisik.
[test_dashboard_ui.py](../test_dashboard_ui.py), [test_inventory_ui.py](../test_inventory_ui.py), dan [test_stages67_ui.py](../test_stages67_ui.py) mencakup ukuran desktop dan akses kontrol.
Nilai skala tes adalah `tk scaling = 96/72` dan `120/72`: 96/120 DPI, setara 100%/125% terhadap dasar 96 DPI, bukan 100%/120%.
Tes Tk tersebut bukan bukti semua pengaturan DPI Windows atau seluruh perangkat kamera telah lolos; kamera fisik tidak diuji dalam penyusunan dokumen ini.

- [ ] Pada 1366×768 dan 1920×1080, ulangi pada skala 100%/125%; catat ukuran viewport yang benar-benar terwujud, bukan hanya ukuran yang diminta.
- [ ] Buka semua halaman; periksa header/sidebar/footer, tombol utama, tabel, badge, saran, dan drawer tanpa teks penting terpotong.
- [ ] Perkecil ke 1000×600 dan Dashboard 1366×700; gulir hingga kontrol bawah/kanan dapat dijangkau, lalu kembali ke ukuran besar.
- [ ] Filter area, klik K03/R02, pastikan sideview K03 menyorot R02 dan memperlihatkan T03–T01; uji navigasi kolom serta lokasi kosong.
- [ ] Uji Up/Down/Home/End dan wheel tabel; pastikan pemilihan dari dialog dapat berpindah halaman tanpa callback ke widget yang sudah ditutup.
- [ ] Dengan kamera laptop/USB nyata, uji mulai/berhenti, pergantian halaman saat Live, beberapa QR, label identik, TTL, QR tidak dikenal, dan daftar yang digulir.
- [ ] Buka scanner ketika Live aktif; uji menutupnya sebelum perangkat siap, setelah capture aktif, serta setelah Live sengaja dimatikan.
- [ ] Dekode QR sebelum konfirmasi tidak boleh menambah hasil; konfirmasi ulang batch tidak boleh menambah baris; selesai sesi harus menolak hasil baru.
- [ ] Uji izin kamera ditolak, perangkat dipakai aplikasi lain, pencabutan USB, pemilihan indeks berbeda, dan fallback input kode manual.
- [ ] Uji status lintas hari pada database uji; bedakan pembaruan inventori/Live dari snapshot pengecekan, serta ulangi preview/impor Excel dengan baris invalid.
- [ ] Catat jarak, ukuran cetak QR, fokus, cahaya, sudut, dan FPS nyata saat uji lapangan; hasil frame sintetis tidak menggantikan pengujian ini.
