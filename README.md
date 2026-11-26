# Macaroni Holic POS (Mobile, Flet)

Aplikasi kasir offline Macaroni Holic untuk HP/tablet Android. Ini versi mobile dari `macaroni_holic_desktop.py`.

## Isi folder

| File | Isi |
|---|---|
| `src/main.py` | Tampilan aplikasi (Flet): tab Kasir, Stok, Laporan |
| `src/core.py` | Logika toko: database SQLite, stok, checkout, struk, CSV |
| `tests/test_core.py` | Tes otomatis untuk logika checkout dan stok |
| `pyproject.toml` | Konfigurasi build APK |

## Coba di komputer

```powershell
pip install "flet[all]==1.1.3"
```

```powershell
flet run src/main.py
```

Untuk melihat tampilan seukuran HP di browser:

```powershell
flet run --web src/main.py
```

## Coba langsung di HP (tanpa build)

1. Pasang aplikasi **Flet** dari Play Store.
2. HP dan komputer harus tersambung ke Wi-Fi yang sama.
3. Jalankan perintah ini di komputer, lalu scan QR code yang muncul pakai aplikasi Flet di HP:

```powershell
flet run --android src/main.py
```

## Build APK

Yang perlu disiapkan (cukup sekali):
- **Flutter SDK**. Kalau belum ada, `flet build` akan menawarkan untuk mengunduhnya otomatis.
- **Android SDK / Android Studio**. Ini juga bisa dipasang otomatis oleh `flet build` kalau belum ada.
- Ruang disk kosong kurang lebih 5–10 GB. Build pertama makan waktu sekitar 10–20 menit.

Jalankan dari folder ini (root repo ini):

```powershell
flet build apk
```

Hasilnya ada di `build/apk/`. Salin file `.apk` ke HP lalu pasang (izinkan "Instal dari sumber tidak dikenal").

Untuk APK yang lebih kecil (satu file per jenis prosesor HP):

```powershell
flet build apk --split-per-abi
```

Pakai file `arm64-v8a` untuk hampir semua HP Android keluaran 2017 ke atas.

## Yang berubah dibanding versi desktop

- Layout dibuat untuk layar HP: navigasi bawah, keranjang muncul dari bawah layar, dan di tablet kartu menu otomatis jadi 2–3 kolom.
- Tombol **Bagikan ke WA** membuka menu Bagikan Android, jadi struk bisa langsung dikirim lewat WhatsApp. Tombol Salin tetap ada.
- Export CSV di HP juga lewat menu Bagikan (bisa ke WA, Drive, email). Di komputer muncul dialog Simpan.
- Laporan bisa difilter **Hari ini** atau **Semua**.
- Item dengan menu dan saus yang sama otomatis digabung di keranjang. Jumlah porsi diatur dengan tombol − dan +.
- Perbaikan bug:
  - Stok dicek ulang ke database saat checkout. Kalau stok tidak cukup, seluruh transaksi dibatalkan.
  - Nomor struk tidak bisa dobel (format `MH-YYYYMMDD-001`, nomor urut harian).
  - Error sintaks di file desktop (string yang terpotong ke baris baru) tidak ikut terbawa.

## Data

Database `macaroni_holic.db` disimpan di folder data aplikasi di HP, jadi tidak hilang saat aplikasi di-update. Datanya hilang kalau aplikasi di-uninstall atau datanya dihapus dari Pengaturan. Untuk cadangan, rutin Export CSV dari tab Laporan.

Skema tabelnya sama dengan versi desktop. Kalau dijalankan di komputer, file `macaroni_holic.db` dari versi desktop bisa ditaruh di folder `src/` dan langsung terbaca.

## Menjalankan tes

```powershell
pip install pytest
```

```powershell
pytest tests
```
