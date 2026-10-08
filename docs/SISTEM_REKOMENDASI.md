# Sistem rekomendasi: aturan, keputusan, dan riwayat

> Salinan untuk repository GitHub. Setup dan data demo repository dijelaskan pada [README](../README.md); path executable/.build dalam dokumen ini mengacu pada workspace asal.

Panduan pengembang berdasarkan kode sumber yang diperiksa pada 4 Oktober 2026.
Semua jalur file di bawah relatif terhadap akar proyek, kecuali tautan Markdown yang relatif terhadap dokumen ini.

## Batas sistem

Sistem ini adalah **mesin aturan untuk demo**, bukan AI yang dilatih atau model prediksi.
Ia menggabungkan umur batch, stok batch, kebutuhan site, dan kecocokan model unit customer yang tercatat eksplisit.
Tidak ada skor pembelajaran, probabilitas, pelatihan model, atau prediksi demand dari histori transaksi.
Label `source='Simulasi'` berarti konteks kebutuhan demo; label tersebut bukan jaminan bahwa kebutuhan masih berlaku di lapangan.
Site A/B/C, Customer A/B/C, dan model unit simulasi adalah contoh data, bukan integrasi kebutuhan operasional.

Rekomendasi terlihat di **Dashboard, Data Barang, dan Live**; pencatatan keputusan berjalan melalui **sesi Pengecekan**.
Dashboard menampilkan ringkasan tujuan utama pada barang terpilih; Data Barang dan Live menampilkan saran serta keputusan terakhir.
Live hanya membaca inventori dan keputusan: pemindaian Live tidak otomatis membuat hasil pengecekan.
Belum ada API keputusan langsung dari inventori tanpa sesi dan hasil pengecekan. Hasil pengecekan dapat ditambahkan dengan ID manual atau QR; kamera tidak wajib.
Menyimpan keputusan atau menandai selesai tidak memindahkan lokasi, mengurangi stok, membuat penawaran, atau menghubungi tujuan.
Pencatatan perubahan inventori/barang keluar merupakan alur terpisah.

## Peta kode dan aliran data

| Tanggung jawab | Sumber utama |
| --- | --- |
| Batas umur dan status | [`warehouse/domain.py`](../warehouse/domain.py), `aging()` |
| Penyaringan, ranking, teks saran, keputusan, penyelesaian | [`warehouse/recommendations.py`](../warehouse/recommendations.py) |
| Pembacaan kebutuhan per material | [`warehouse/recommendation_data.py`](../warehouse/recommendation_data.py) |
| Skema, CHECK, indeks, trigger, migrasi v5–v7 | [`warehouse/database.py`](../warehouse/database.py) |
| Snapshot scan dan penguncian sesi | [`warehouse/sessions.py`](../warehouse/sessions.py) |
| Pemilihan saran untuk Draft/riwayat dan form keputusan | [`warehouse/session_ui.py`](../warehouse/session_ui.py) |
| Proyeksi inventori, Dashboard, Live | [`warehouse/ui.py`](../warehouse/ui.py), [`warehouse/dashboard_ui.py`](../warehouse/dashboard_ui.py), [`warehouse/live_ui.py`](../warehouse/live_ui.py) |
| Data laporan, Excel, PDF | [`warehouse/reports.py`](../warehouse/reports.py) |
| Pembuatan enam skenario contoh | [`scripts/create_trial_data.py`](../scripts/create_trial_data.py), `_seed_recommendation_scenarios()` |

Alur baca: `batches` → `recommendation_context(db, material)` → `recommend_for(item, context=...)` → tampilan.
Alur catat: `Sessions.start()` → `Sessions.add_code()` → `RecommendationService.save_decision()` → `Sessions.finish()`.
Penyelesaian tindak lanjut dicatat terpisah melalui `RecommendationService.complete()`.

## Konteks kebutuhan

`recommendation_context(db, material)` mengembalikan dictionary:

```python
{'source': 'Simulasi',
 'sites': [{'site': 'A', 'demand_prev': 3, 'demand_now': 9,
            'open_demand': 10, 'site_stock': 1}],
 'customers': [{'customer': 'A', 'unit_model': 'UNIT-X', 'open_demand': 4}]}
```

- `site_demand`: kunci `(material, site)`; dibaca dengan kecocokan material tepat dan diurutkan menurut `site`.
- `material_unit_compatibility`: kunci `(material, unit_model)`; menghubungkan material ke model unit.
- `customer_demand`: kunci `(customer, unit_model)`; di-join melalui model yang kompatibel, lalu diurutkan `customer, unit_model`.
- Material tanpa pemetaan menghasilkan `sites=[]`, `customers=[]`, `source='Simulasi'`; tidak dibuatkan tujuan baru saat dibaca.
- Pemanggil aplikasi umumnya mengubah konteks tanpa kedua jenis baris menjadi `None`; saran lalu hanya berbasis umur.
- `context=None` menghasilkan saran tanpa field `source/options`. Konteks eksplisit, termasuk yang kosong, menambahkan kedua field itu.
- DB saat ini membatasi kode site/customer ke A/B/C; seluruh besaran kebutuhan/stok site berupa integer nonnegatif.

Generator data uji juga membuat kebutuhan deterministik bagi material lain yang sudah ada pada saat generasi.
Pemetaan tambahan itu dibuat dan disimpan saat pembuatan dataset; material yang diimpor kemudian tidak mendapat tujuan buatan.
Tidak ada timestamp kebutuhan atau masa kedaluwarsa konteks di ketiga tabel ini.

## Aturan umur dan urutan cabang

`age = (today - date.fromisoformat(received_date)).days`; `today` default adalah tanggal komputer.
Nilai default dari `domain.py`: `normal_max=30`, `age_limit=90`; syarat batas adalah `0 <= normal_max < age_limit`.
Normal berarti `age <= normal_max`, Warning berarti `normal_max < age <= age_limit`, selebihnya Melewati batas.
Tanggal masa depan ditolak. `stock` harus tepat bertipe `int` dan nonnegatif; boolean, float, atau string tidak diterima mesin aturan.
Validasi tanggal/umur dijalankan sebelum cabang stok nol: stok nol dengan tanggal rusak tetap menghasilkan kesalahan data.

| Urutan/kondisi | `code` / `priority` | Opsi tujuan dan perilaku |
| --- | --- | --- |
| Data tanggal/stok/batas tidak valid | `DATA_PERLU_DIPERBAIKI` / 3 | Perbaiki data; opsi kosong jika konteks diberikan. |
| Data valid, `stock == 0` | `STOK_HABIS` / 0 | Tidak ada tindak lanjut fisik; opsi kosong. |
| Melewati batas | `MELEWATI_BATAS` / 3 | Periksa fisik segera; semua customer valid, lalu semua site dengan kekurangan valid. |
| Warning | `WARNING` / 2 | Hanya customer valid; bila ada, judul/tindakan memakai customer peringkat pertama. |
| Normal dan `normal_max + 1 - age <= 7` | `NORMAL_DEKAT_WARNING` / 1 | Site dengan demand naik dan kekurangan; opsi pertama dapat mengganti judul/tindakan. |
| Normal lainnya | `NORMAL` / 0 | Aturan site sama; jika ada baris site tetapi tidak ada opsi, judul menjadi “Aman, belum perlu tindakan”. |

Dengan batas default, kode `NORMAL_DEKAT_WARNING` berlaku pada umur 24–30 hari.
Sisa hari menuju Warning adalah `normal_max + 1 - age`; menuju Melewati batas adalah `age_limit + 1 - age`.
Judul yang berubah menjadi relokasi/penawaran tidak mengubah `code`, prioritas, atau status aging barang.
Tidak adanya opsi Normal berarti kriteria relokasi belum terpenuhi; itu tidak membuktikan semua kebutuhan site telah terpenuhi.
Merah dengan konteks kosong menyatakan tujuan belum dapat ditentukan; tanpa konteks, teksnya berupa saran umur umum.

## Formula kandidat dan ranking persis

### Site

`_site_options(sites, stock, rising_only=..., after_check=...)` menerima baris jika:

1. `site` berupa string yang tidak kosong setelah `strip()`.
2. `demand_prev`, `demand_now`, `open_demand`, `site_stock` masing-masing tepat `int` dan `>= 0`.
3. `demand_now > 0` dan `open_demand > site_stock`.
4. Khusus Normal (`rising_only=True`): `demand_now - demand_prev >= 2` **dan** `5 * demand_now >= 6 * demand_prev`.

Syarat terakhir setara kenaikan setidaknya 2 unit dan sekurangnya 20% dari nilai sebelumnya, tanpa pembagian.
Jika nilai sebelumnya nol, persamaan perkalian otomatis lolos, tetapi kenaikan 2 unit tetap wajib.
Untuk Melewati batas, tidak ada syarat kenaikan: demand stabil atau menurun tetap dapat menjadi kandidat jika syarat 1–3 lolos.
`shortage = open_demand - site_stock`; `suggested_units = min(stock_batch, shortage)`.

### Customer

`_customer_options(customers, stock)` mensyaratkan `customer` dan `unit_model` string tidak kosong setelah `strip()`.
`open_demand` harus tepat `int` dan `> 0`; `suggested_units = min(stock_batch, open_demand)`.
Kecocokan material-model dijamin oleh query `recommendation_context()`, bukan diperiksa ulang oleh helper ini.
Pemanggil yang memasok konteks buatan harus menjaga kecocokan tersebut sendiri.

### Pengurutan dan makna jumlah

Masing-masing kelompok diurutkan dengan kunci `(-suggested_units, target)`: jumlah menurun, lalu kode tujuan menaik.
`target` merupakan nama/kode yang sudah di-`strip()`; pembandingan string memakai urutan Python, bukan pengurutan bahasa alami.
Pada Merah, hasil akhir adalah `customer_options + site_options`, bukan satu ranking gabungan.
Customer 3 unit tetap muncul sebelum site 14 unit. Pada Normal hanya kelompok site, pada Warning hanya kelompok customer.
Jika satu customer memiliki beberapa model kompatibel, setiap baris dapat menghasilkan opsi sendiri; kebutuhan tidak dijumlahkan/dideduplikasi.
Untuk nilai kunci yang benar-benar sama, sort stabil mempertahankan urutan input.
Jumlah opsi adalah usulan per alternatif, bukan alokasi stok bersama, pemesanan, atau kuantitas keputusan yang sudah dieksekusi.

## Kontrak API utama

| API | Input dan hasil |
| --- | --- |
| `recommend_for(item, *, normal_max=30, age_limit=90, today=None, context=None)` | Minimal `item['received_date']` ISO dan `item['stock']` integer. Hasil dictionary `code, title, reason, next_action, priority`; dengan konteks ditambah `source, options`. Tidak menulis DB. |
| Opsi dalam `options` | Dictionary `kind` (`site/customer`), `target`, `title`, `reason`, `next_action`, `suggested_units`. |
| `recommendation_context(db, material)` | Koneksi DB dan kode material; hasil konteks terstruktur di atas. |
| `Sessions.add_code(session_id, code)` | ID batch atau `ID:<batch>` dalam Draft; hasil `(batch_id, is_new)`; membuat snapshot hanya pada scan pertama. |
| `RecommendationService(db).save_decision(session_id, batch_id, physical_condition, choice, reason, *, target_kind=None, target_code=None)` | Memvalidasi dan menyimpan/memperbarui satu keputusan per sesi/batch; hasil dictionary keputusan terurai. |
| `for_result(session_id, batch_id)` | Keputusan untuk satu hasil scan, atau `None`. |
| `latest_action_for_batch(batch_id)` | Keputusan terbaru lintas sesi, diurutkan `decided_at DESC, id DESC`, atau `None`; termasuk keputusan dari Draft. |
| `complete(decision_id, officer, note)` | ID positif bertipe `int`, petugas 1–100 karakter, catatan 1–2000 karakter setelah trim; hasil keputusan dengan penyelesaian. |
| `advice_for_result(db, session, item, decision=None)` | Proyeksi saran untuk detail sesi; memilih sumber sesuai tabel waktu berikut. |
| `report_data(db, session_id)` | Dictionary `session, rows, counts, generated_at`; tiap baris memiliki `recommendation` dan `decision` atau `None`. |

Hasil keputusan berisi identitas sesi/batch, kondisi, pilihan, tujuan, alasan, petugas, waktu, umur/status saat keputusan,
field `recommendation_*`, `recommendation_snapshot`, `action_status`, serta `completed_at/completed_by/completion_note`.
Kegagalan validasi layanan berupa `ValueError`; pembatas DB juga dapat menghasilkan `sqlite3.Error`.

## Keputusan petugas dan gate “Layak”

Kondisi yang diterima persis: `Layak`, `Perlu evaluasi`, `Tidak layak`; alasan wajib 1–2000 karakter setelah trim.

| `choice` | Harus Layak? | Pembatas tambahan |
| --- | --- | --- |
| `Pindahkan ke site` | Ya | `target_kind='site'`, kode tujuan harus ada dalam opsi terkini. |
| `Tawarkan ke customer` | Ya | `target_kind='customer'`, kode tujuan harus ada dalam opsi terkini. |
| `Perlu dipindahkan` | Ya | Status terkini dengan batas sesi harus Melewati batas; tanpa target eksplisit. |
| `Prioritaskan pemakaian` | Ya | Tanpa target eksplisit; tidak dibatasi satu status umur. |
| `Tunda evaluasi` | Tidak | Tanpa target; tetap merupakan tindakan belum selesai. |
| `Tidak perlu tindakan` | Tidak | Tanpa target; tidak dapat diberi completion. |

Urutan `CHOICES` di layanan adalah empat pilihan umum terakhir di tabel, lalu `Pindahkan ke site`, `Tawarkan ke customer`.
Form menempatkan pilihan site yang tersedia, lalu customer yang tersedia, kemudian empat pilihan umum tersebut.
Pilihan target lama tetap dapat ditampilkan ketika membuka Draft, tetapi target yang hilang dikosongkan dan pengguna diminta memilih ulang.
Saran sendiri tidak memeriksa fisik: gate “Layak” diterapkan saat menyimpan keputusan, termasuk relokasi untuk barang Normal.

Syarat simpan lain: sesi ada dan Draft, batch sudah discan di sesi itu, batch masih ada dan stoknya positif.
Keputusan yang sudah memiliki completion tidak bisa diedit; tindakan belum selesai dari sesi lain memblokir keputusan baru untuk batch sama.
Pengecualian tindakan terbuka adalah pilihan `Tidak perlu tindakan`; revisi keputusan dalam sesi yang sama tetap diperbolehkan sebelum selesai.
Petugas keputusan diambil dari `check_sessions.officer`; API simpan tidak menerima petugas pengganti.

### Menghadapi rekomendasi yang sudah berubah

`save_decision()` membuka `BEGIN IMMEDIATE`, membaca inventori dan kebutuhan lagi, lalu menghitung ulang memakai tanggal lokal saat simpan dan batas sesi.
Target dipadankan persis berdasarkan pasangan `kind/target` terhadap opsi hasil hitung ulang; target hilang atau jenis salah ditolak.
Stok habis, perubahan umur, atau perubahan demand sejak dialog dibuka karena itu dapat menggagalkan simpan.
Transaksi commit hanya jika seluruh pemeriksaan lolos; exception memicu rollback. Transaksi lain yang masih aktif ditolak di awal.
Ini validasi terhadap data DB terkini, bukan pemeriksaan umur data kebutuhan atau pembandingan versi dialog.
Jika target tetap valid tetapi jumlah/alasan berubah, simpan memakai saran hasil hitung ulang tanpa meminta konfirmasi versi.

## Waktu, snapshot, penyelesaian, dan laporan

| Permukaan/rekaman | Data yang digunakan |
| --- | --- |
| Data Barang / Dashboard / Live | Inventori, kebutuhan, dan tanggal saat ini, dengan batas default; keputusan terakhir tampil terpisah. Live tanpa stok tidak menampilkan saran aktif. |
| `check_results.snapshot` | Inventori dan `recommendation_at_check` saat scan pertama; `age/status/checked_at` juga tersimpan. Scan ulang tidak mengganti snapshot/waktunya. |
| Detail sesi Draft | `advice_for_result()` menghitung ulang dari inventori/kebutuhan saat ini dengan batas sesi, walaupun ada keputusan tersimpan. |
| `recommendation_decisions` | Snapshot saran hasil hitung ulang pada simpan keputusan, umur/status saat keputusan, pilihan, alasan, petugas, tujuan. Revisi Draft memperbarui baris yang sama. |
| Detail sesi Selesai | Jika ada keputusan: `recommendation_snapshot` keputusan. Jika tidak: `recommendation_at_check`; data lama tanpa snapshot saran dihitung dengan tanggal scan. |
| `recommendation_completions` | Rekaman terpisah satu kali per keputusan: petugas, waktu, catatan selesai. Tidak mengubah snapshot keputusan atau inventori. |
| `report_data()` / Excel / PDF | Inventori/umur/status dan rekomendasi **saat scan**, serta field keputusan tersimpan yang dipilih eksplisit. Completion/status aksi terkini tidak disertakan. |

Draft memakai snapshot scan sebagai hasil pengecekan, tetapi detail sarannya bisa menunjukkan kondisi saat ini; keduanya dapat berbeda.
Laporan juga dapat memuat rekomendasi saat scan yang berbeda dari snapshot keputusan yang dibuat kemudian; ini perilaku kode saat ini.
Fallback laporan lama tanpa `recommendation_at_check` menghitung dari snapshot inventori pada tanggal scan tanpa menarik kebutuhan terbaru.
Snapshot keputusan bukan log setiap revisi: nilai sebelumnya tertimpa selama Draft masih boleh diedit.
Setelah sesi selesai, trigger DB mengunci keputusan; keputusan juga terkunci setelah completion. Penghapusan keputusan dilarang.
Completion tidak bisa diubah/dihapus; layanan mengizinkan completion saat Draft maupun Selesai, sedangkan tombol UI tersedia pada detail sesi Selesai.
`action_status` adalah `Selesai` jika ada completion, `Tidak perlu tindakan` untuk pilihan tersebut, selainnya `Belum selesai`.
`Sessions.finish()` memerlukan minimal satu hasil scan, tetapi tidak mewajibkan keputusan atau completion setiap barang.

## Contoh UJI-REC-001 sampai UJI-REC-006

Contoh berikut berasal dari generator dataset uji, bukan dari `seed_demo()` standar yang membuat batch `DEMO-*`.
Gunakan tanggal acuan **T yang sama dengan tanggal pembuatan dataset** dan batas default 30/90 untuk mereproduksi tabel ini.
Generator menyimpan `received_date = T - umur`; tanggal masuk tidak bergeser otomatis ketika aplikasi dibuka lagi.

| Batch / material | Umur di T; stok | Bukti kebutuhan yang relevan | Opsi berurutan di T |
| --- | --- | --- | --- |
| `UJI-REC-001` / `MAT-REC-001` | 12 hari; 20 | Site A: 3→9, open 10, stok site 1 | Normal; Site A, `min(20,10-1)=9` unit. |
| `UJI-REC-002` / `MAT-REC-002` | 12 hari; 8 | A: open 0/stok 12; B: 1/5; C: 0/6 | Normal; tidak ada opsi, “Aman, belum perlu tindakan”. |
| `UJI-REC-003` / `MAT-REC-003` | 60 hari; 7 | Customer A, model `UNIT-CUSTOMER-A-WARNING`, open 4 | Warning; Customer A, 4 unit setelah cek fisik. |
| `UJI-REC-004` / `MAT-REC-004` | 120 hari; 10 | Customer A, model `UNIT-CUSTOMER-A-CRITICAL`, open 3 | Melewati batas; Customer A, 3 unit jika layak. |
| `UJI-REC-005` / `MAT-REC-005` | 180 hari; 15 | Site B: 3→12, open 15, stok site 1; tanpa customer | Melewati batas; Site B, 14 unit jika layak. |
| `UJI-REC-006` / `MAT-REC-006` | 240 hari; 20 | Customer A open 5, model `UNIT-CUSTOMER-A-CHOICE`; Site C: 4→14, open 12, stok 1 | Melewati batas; Customer A 5 unit, lalu Site C 11 unit. |

Pada T+19, dua batch Normal yang berumur 12 hari sudah menjadi Warning; aturan opsi berubah menjadi customer saja.
Pada T+31, `UJI-REC-003` mencapai umur 91 hari dan menjadi Melewati batas.
Jangan menguji status dengan tanggal komputer yang tidak cocok dengan T lalu menganggap perubahan tersebut regresi.

## Titik modifikasi aman dan uji

- Ubah formula/urutan di `recommendations.py`; pertahankan kontrak field agar seluruh tampilan dan ekspor tetap bisa membacanya.
- Ubah sumber kebutuhan melalui `recommendation_data.py`; pertahankan kecocokan material-model dan jangan menebak kebutuhan material baru.
- Menambah kode tujuan/jenis pilihan perlu menyelaraskan layanan, form, CHECK/migrasi di `database.py`, tampilan tujuan, dan ekspor.
- Mengubah aturan histori perlu memeriksa `sessions.py`, `advice_for_result()`, `report_data()`; jangan menghitung ulang laporan lama dari inventori terkini.
- Gunakan DB sementara untuk eksperimen/generasi ulang; perubahan fixture generator tidak memperbarui snapshot atau DB yang sudah dibagikan.

Jalankan dari akar proyek setelah menetapkan `$projectPython` sesuai [panduan lingkungan](PANDUAN_PENGEMBANG.md#3-menjalankan-kode):

```powershell
& $projectPython -B -m unittest test_recommendations test_recommendation_context test_recommendation_history test_recommendation_reports test_session_recommendation_display tests.test_recommendation_data
```

Kelompok ini memeriksa aturan, kondisi Layak/tujuan, snapshot, completion, ekspor, migrasi, dan data kompatibilitas. Bukti rilis 4 Oktober 2026 mencatat 148 tes gabungan lulus; rujukan: catatan verifikasi rilis (`exe_update_20261004.json`; referensi workspace asal).
Untuk perubahan tampilan, tambahkan `test_recommendation_surfaces`, `test_recommendation_ui`, `test_dashboard_recommendation_ui`, dan `tests.test_recommendation_views`.
Untuk generator, jalankan `& $projectPython -B -m unittest tests.test_trial_data`; tes memakai direktori sementara.
Tambahkan kasus batas sesuai perubahan: umur 30/31/90/91, kenaikan tepat 2 unit/20%, prev nol, tie ranking, stok nol, target berubah saat dialog terbuka.

## Ringkasan dan batas yang perlu dijaga

Rekomendasi adalah alternatif berbasis aturan; petugas mencatat keputusan dan pemeriksaan fisik dalam sesi.
Waktu scan, waktu keputusan, dan waktu penyelesaian merupakan tiga kejadian berbeda dengan penyimpanan berbeda.
Kebutuhan simulasi belum memiliki masa berlaku, opsi customer multi-model belum diagregasi, dan `suggested_units` belum menjadi kuantitas tindakan.
Label saran yang dilihat sebelum simpan dapat berbeda dari snapshot hasil hitung ulang; perubahan yang masih menyisakan target valid tidak dideteksi sebagai konflik versi.
Pertahankan batas ini saat menjelaskan fitur atau menambah integrasi; jangan menyatakan alokasi otomatis, eksekusi transfer, atau keputusan inventori langsung sudah tersedia.
