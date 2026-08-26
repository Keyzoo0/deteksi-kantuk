# Deteksi Rasa Kantuk (Drowsiness Detection)

Deteksi rasa kantuk secara real-time dari **mata** dan **mulut** menggunakan webcam.
Target akhir: **Raspberry Pi 5 (8 GB) + webcam USB**, tetapi program ini juga bisa
langsung dicoba di PC/laptop Linux.

Status ditampilkan sebagai teks besar di jendela video: **AMAN** (hijau) atau
**KANTUK** (merah), lengkap dengan alasannya.

---

## Cara kerja

| Sinyal | Rumus | Untuk apa |
|---|---|---|
| **EAR** (Eye Aspect Ratio) | jarak vertikal kelopak ÷ (2 × lebar mata) | seberapa terbuka mata |
| **PERCLOS** | % waktu mata tertutup dalam 60 detik terakhir | indikator kantuk paling baku di literatur |
| **MAR** (Mouth Aspect Ratio) | bukaan bibir ÷ lebar mulut | mendeteksi menguap |

Landmark wajah diambil dari **MediaPipe Face Mesh** (468 titik), jadi EAR dan MAR
dihitung dari titik kelopak mata dan bibir yang sebenarnya — bukan tebakan dari
kotak deteksi.

### Kalibrasi

Saat mulai, program merekam ±4 detik kondisi wajah normal pengguna (mata terbuka
wajar, mulut tertutup) dan mengambil **median**-nya sebagai *baseline*. Semua
penilaian setelah itu memakai **rasio terhadap baseline**, bukan angka mutlak.

Alasannya: nilai EAR mutlak berbeda-beda antar orang (bentuk mata), antar jarak ke
kamera, dan antar resolusi webcam. Ambang tetap seperti `EAR < 0.21` sering meleset
untuk mata sipit atau pengguna berkacamata. Dengan kalibrasi, ambang menyesuaikan
otomatis ke pengguna yang sedang duduk di depan kamera.

Tekan **`c`** kapan saja untuk kalibrasi ulang (mis. setelah ganti posisi duduk).

### Kapan dinyatakan KANTUK

Salah satu saja terpenuhi sudah cukup:

1. Mata terpejam menerus **> 1,2 detik** (EAR < 62% baseline)
2. **PERCLOS > 28%** dalam 60 detik terakhir
3. **Menguap ≥ 3×** dalam satu menit (MAR > 190% baseline selama ≥ 0,9 detik)

Kedipan normal (< 0,5 detik) tidak dihitung sebagai terpejam, dan mulut menganga
sesaat (bicara) tidak dihitung sebagai menguap.

---

## Instalasi

### Di PC/laptop Linux

```bash
./setup.sh     # bikin .venv + pasang dependensi
./run.sh       # jalankan
```

> **Catatan Python:** MediaPipe hanya punya wheel untuk **Python 3.9–3.12**.
> Kalau sistem Anda hanya punya Python 3.13/3.14 (mis. Ubuntu 26.04), `setup.sh`
> otomatis mengunduh Python 3.12 lewat [`uv`](https://github.com/astral-sh/uv) ke
> folder pengguna — **tanpa sudo** dan tanpa mengubah Python bawaan sistem.

### Di Raspberry Pi 5 (Raspberry Pi OS Bookworm)

```bash
./setup_raspi.sh   # apt + venv + pip (Python 3.11 bawaan sudah cocok)
./run.sh
```

MediaPipe menyediakan wheel `aarch64` untuk Python 3.11, jadi tidak perlu compile.
Perkiraan performa pada 640×480: **±15–20 FPS** di Pi 5 — cukup untuk deteksi kantuk.

Tips di Pi 5:
- Pakai webcam USB yang mendukung **MJPG** (sudah diminta otomatis oleh program).
- Kalau berat, turunkan resolusi di `config.json` ke `320×240`.
- Pastikan pendingin/heatsink terpasang bila dipakai lama.

---

## Pemakaian

```bash
./run.sh                      # kamera default (index 0)
./run.sh --sumber 1           # pilih webcam lain
./run.sh --sumber video.mp4   # uji dari file video
./run.sh --kalibrasi 6        # kalibrasi 6 detik
./run.sh --tanpa-jendela      # headless, status dicetak ke terminal
./run.sh --debug              # tampilkan seluruh 468 landmark
```

Tombol saat jendela aktif:

| Tombol | Fungsi |
|---|---|
| `q` / `Esc` | keluar |
| `c` | kalibrasi ulang |
| `d` | tampilkan/sembunyikan landmark |

Bingung webcam mana yang aktif:

```bash
.venv/bin/python tools/cek_kamera.py
```

---

## Konfigurasi

Semua ambang ada di `config.json` — bisa diubah tanpa menyentuh kode.

```jsonc
{
  "kamera": {
    "sumber": "0",            // index webcam atau path file video
    "lebar": 640, "tinggi": 480, "fps": 30,
    "flip_horizontal": true   // tampilan cermin
  },
  "ambang": {
    "rasio_mata_tertutup": 0.62,     // EAR < 62% baseline = terpejam
    "durasi_terpejam_detik": 1.2,    // terpejam selama ini -> KANTUK
    "perclos_window_detik": 60.0,
    "perclos_kantuk": 0.28,          // >28% -> KANTUK
    "durasi_kedip_maks": 0.5,        // batas atas durasi satu kedipan
    "rasio_mulut_menguap": 1.9,      // MAR > 190% baseline = menganga
    "durasi_menguap_detik": 0.9,
    "menguap_per_menit_kantuk": 3
  },
  "kalibrasi_detik": 4.0,
  "tampilkan_jendela": true
}
```

**Terlalu sering false alarm?** Naikkan `durasi_terpejam_detik` (mis. 1.5) atau
turunkan `rasio_mata_tertutup` (mis. 0.55).
**Kurang sensitif?** Lakukan sebaliknya.

---

## Struktur project

```
deteksi-kantuk/
├── src/
│   ├── main.py       # loop utama: kamera -> deteksi -> penilaian -> tampilan
│   ├── config.py     # dataclass konfigurasi + pembaca config.json
│   ├── kamera.py     # pembukaan webcam (V4L2, MJPG) + penanganan galat
│   ├── deteksi.py    # MediaPipe Face Mesh -> EAR & MAR
│   ├── metrik.py     # kalibrasi, PERCLOS, hitung kedip & menguap, level kantuk
│   └── tampilan.py   # overlay OpenCV (kontur mata/mulut, panel metrik, banner)
├── tools/cek_kamera.py
├── config.json
├── setup.sh / setup_raspi.sh / run.sh
└── requirements.txt
```

---

## Batasan yang perlu diketahui

- **Butuh cahaya cukup.** Webcam biasa gagal di gelap — untuk pemakaian malam
  perlu kamera NoIR + LED inframerah.
- **Kacamata dengan pantulan kuat** bisa menurunkan akurasi landmark mata.
- Program hanya melacak **satu wajah** (yang paling jelas terlihat).
- Menguap dan berbicara lama bisa mirip; karena itu menguap harus bertahan
  ≥ 0,9 detik sebelum dihitung.
- Ini prototipe demo, **bukan alat keselamatan bersertifikasi**.
