# Asisten Monitoring Rasa Kantuk (Drowsiness Detection)

Deteksi rasa kantuk secara real-time dari **mata** dan **mulut** menggunakan webcam,
lengkap dengan **asisten suara Bahasa Indonesia** yang menuntun dan memperingatkan
pengemudi lewat speaker. Target akhir: **Raspberry Pi 5 (8 GB) + webcam Logitech
USB**, tetapi program ini juga bisa langsung dicoba di PC/laptop Linux.

Status ditampilkan sebagai teks besar di jendela video: **AMAN** (hijau) atau
**KANTUK** (merah), lengkap dengan alasannya.

Alurnya tiga tahap:

| Tahap | Yang terjadi | Suara |
|---|---|---|
| **SIAGA** | Kamera belum menyala, menunggu tombol **SPASI** | *"Halo, saya asisten pribadi monitoring rasa kantuk saat berkendara. Tekan tombol spasi untuk memulai sistem."* |
| **KALIBRASI** | Kamera menyala, menunggu wajah masuk bingkai lalu merekam baseline | *"Arahkan kamera ke wajah Anda"* (tiap 5 detik selama wajah belum terlihat), lalu *"Memulai kalibrasi. Arahkan dan tahan wajah Anda menghadap ke kamera"*, ditutup *"Kalibrasi selesai. Sistem monitoring dimulai."* |
| **MONITOR** | Penilaian kantuk tiap frame | *"Anda sedang mengantuk, silakan menepi"* saat mengantuk; *"Arahkan kamera ke wajah Anda"* saat wajah keluar bingkai |

Bila wajah **hilang lebih dari 1 menit** saat monitoring, sistem mengucapkan
*"Wajah tidak terdeteksi lebih dari satu menit. Sistem dimatikan"*, mencetak
ringkasan sesi, mematikan kamera, dan kembali ke SIAGA — tekan **SPASI** untuk
memulai lagi dari awal.

---

## Cara kerja

| Sinyal | Rumus | Untuk apa |
|---|---|---|
| **EAR** (Eye Aspect Ratio) | jarak vertikal kelopak ÷ (2 × lebar mata) | seberapa terbuka mata |
| **PERCLOS** | % waktu mata tertutup dalam 60 detik terakhir | indikator kantuk paling baku di literatur |
| **MAR** (Mouth Aspect Ratio) | bukaan bibir ÷ lebar mulut | mendeteksi menguap |

Mata memakai ambang **relatif** terhadap baseline, mulut memakai ambang
**mutlak**. Sebabnya: saat kalibrasi bibir terkatup rapat sehingga baseline MAR
nyaris nol (terukur 0,008 pada video uji) — rasio terhadap angka sekecil itu
meledak, tersenyum saja bisa terbaca 1400% baseline. MAR sendiri sudah
dinormalisasi terhadap lebar mulut sehingga cukup seragam antar orang: pada
video uji mulut biasa 0,01–0,02 sedangkan menguap 0,72–0,97.

Landmark wajah diambil dari **MediaPipe FaceLandmarker** (478 titik, penomoran
sama dengan Face Mesh), jadi EAR dan MAR dihitung dari titik kelopak mata dan
bibir yang sebenarnya — bukan tebakan dari kotak deteksi.

Program memakai **MediaPipe Tasks API**, bukan `mp.solutions.face_mesh` yang lama.
Alasannya: API lama sudah dihapus pada MediaPipe 1.0, sedangkan Tasks API jalan
di MediaPipe 0.10.x maupun 1.x — jadi kode yang sama dipakai di laptop dan di
Raspberry Pi tanpa peduli versi paketnya. Berkas model (`face_landmarker.task`,
±3,8 MB) diunduh otomatis saat pertama kali dijalankan.

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
3. **Sedang menguap** — MAR > 0,50 bertahan ≥ 0,9 detik. Status kembali AMAN
   begitu mulut menutup; menguap tidak "menahan" alarm selama semenit.

PERCLOS baru ikut dinilai setelah jendela pengamatan terisi ≥ 30 detik. Tanpa
syarat itu, satu kedipan panjang di detik-detik awal bisa terbaca 50%.

Kedipan normal (< 0,5 detik) tidak dihitung sebagai terpejam, dan mulut menganga
sesaat (bicara) tidak dihitung sebagai menguap.

---

## Asisten suara

Peringatan diucapkan dari **berkas WAV yang sudah jadi** di folder `suara/`,
bukan disintesis saat program berjalan. Alasannya:

* Suaranya **TTS neural Bahasa Indonesia** (`id-ID-GadisNeural` /
  `id-ID-ArdiNeural`) — jauh lebih enak didengar daripada espeak yang robotik.
* **Tidak perlu internet** dan hampir tanpa beban CPU saat berkendara; ini
  penting di Raspberry Pi.
* Peringatan **langsung berbunyi**, tanpa jeda sintesis.

Kalau berkas WAV-nya hilang, program otomatis jatuh ke TTS sistem
(`espeak-ng`/`spd-say`) — robotik, tetapi lebih baik daripada bisu.

### Kapan bersuara

| Pesan | Pemicu |
|---|---|
| "Anda sedang mengantuk, silakan menepi" | mata terpejam **> 3 detik**, atau menguap **> 2 detik** |
| "Arahkan kamera ke wajah Anda" | wajah tidak terlihat **> 3 detik** |
| "Wajah tidak terdeteksi… sistem dimatikan" | wajah hilang **> 60 detik** saat monitoring |

Pesan yang sama paling cepat diulang tiap **5 detik** (`jeda_ulang_detik`),
jadi asisten tidak cerewet. Ambang suara sengaja **lebih longgar** daripada
ambang tulisan KANTUK di layar (terpejam 1,2 detik): layar boleh bereaksi
cepat, speaker baru bicara kalau kondisinya sudah meyakinkan.

### Uji dan ganti suara

```bash
.venv/bin/python tools/cek_suara.py              # dengarkan semua pesan
.venv/bin/python tools/cek_suara.py --pesan mengantuk
```

Ganti ke suara laki-laki: setel `"voice": "ardi"` di `config.json` (berkasnya
sudah ikut di folder `suara/`). Untuk mengganti **kalimatnya**, rekam ulang —
butuh internet dan dua paket tambahan yang tidak dipakai program utama:

```bash
uv pip install edge-tts soundfile
.venv/bin/python tools/buat_suara.py             # semua pesan, dua suara
.venv/bin/python tools/buat_suara.py --hanya mengantuk \
    --teks mengantuk="Bapak sudah mengantuk, tolong menepi"
```

Kalimat baku pesan ada di `src/suara.py` (`PESAN`) — satu sumber untuk berkas
WAV maupun TTS cadangan.

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

### Menyiapkan Raspberry Pi tanpa monitor (headless)

Kalau Pi tidak punya monitor/keyboard, siapkan kartu SD-nya dulu dari laptop
ini — **tancapkan kartu SD hasil Raspberry Pi Imager**, lalu:

```bash
sudo ./tools/siapkan_raspi.sh                       # pakai WiFi laptop ini
sudo ./tools/siapkan_raspi.sh --pengguna haris --sandi 1 --nama-host raspberrypi
```

Skrip itu mencari partisi kartu SD lewat label (`bootfs`/`rootfs`, bukan
menebak `/dev/sdX`), menolak jalan bila yang ketemu ternyata disk sistem, lalu:

* membuat **pengguna + sandi** (hash SHA-512, bukan teks polos),
* **menyalakan SSH** (berkas `ssh`, sekaligus symlink `ssh.service` di rootfs),
* menyalin **SSID dan sandi WiFi laptop ini** dari NetworkManager — sandinya
  dibaca langsung oleh skrip dan tidak pernah ditampilkan di layar,
* memasang **kunci SSH publik** Anda supaya login tanpa sandi (lewat
  `[ssh] authorized_keys` dan `/etc/skel/.ssh/authorized_keys`),
* mengisi **kode negara WiFi** — tanpa ini radio WiFi Raspberry Pi OS terkunci.

Cara pengaturannya menyesuaikan citra — diperiksa dari rootfs kartu, bukan
ditebak dari versi OS:

| Yang ada di citra | Cara yang dipakai |
|---|---|
| `raspberrypi-sys-mods/init_config` | `custom.toml` |
| `raspberrypi-sys-mods/imager_custom` saja | `firstrun.sh` + `systemd.run=` di `cmdline.txt` (persis cara Raspberry Pi Imager), ditambah `userconf.txt` |
| tidak keduanya | klasik: `userconf.txt` + `wpa_supplicant.conf` |

Ini bukan detail sepele: **Raspberry Pi OS 13 (Trixie) menyediakan
`imager_custom` tanpa `init_config`**, sehingga `custom.toml` diabaikan
diam-diam — Pi ikut boot tanpa pengguna sama sekali dan tidak bisa di-SSH.
Karena itu penentunya `init_config`, bukan `imager_custom`.

SSH sendiri aman di semua jalur karena `sshswitch.service` bawaan citra membaca
penanda `/boot/firmware/ssh`. Berkas `firstrun.sh` bawaan Imager (kalau Anda
sempat mengisi opsi di Imager) dinonaktifkan lebih dulu agar tidak bentrok, dan
`firstrun.sh` buatan skrip ini menghapus dirinya sendiri setelah boot pertama —
termasuk sandi WiFi yang sempat tersimpan di dalamnya.

Setelah kartu dilepas dan Pi dinyalakan, tunggu 1–2 menit (boot pertama
memperluas partisi lalu reboot sendiri), lalu dari laptop:

```bash
ssh haris@raspberrypi.local
# kalau .local tidak jalan, cari IP-nya di jaringan:
ip neigh | grep -iE 'b8:27:eb|dc:a6:32|e4:5f:01|d8:3a:dd'   # MAC Raspberry Pi
```

Lewat kabel LAN caranya sama — Pi mengambil IP dari DHCP dan SSH-nya sudah
menyala, jadi `ssh haris@raspberrypi.local` tetap berlaku.

### Di Raspberry Pi 5 (Raspberry Pi OS Bookworm)

```bash
./setup_raspi.sh   # apt + venv + pip (Python 3.11 bawaan sudah cocok)
./run.sh
```

MediaPipe menyediakan wheel `aarch64` untuk Python 3.11, jadi tidak perlu compile.

Perkiraan performa: inferensi landmark memakan **±11 ms/frame** pada laptop x86
yang dipakai menguji (≈90 FPS teoretis), sehingga FPS nyata ditentukan webcam —
terukur **30 FPS** pada 640×480. Di Pi 5 inferensi lebih berat, perkirakan
**±15–20 FPS**, dan itu sudah cukup: PERCLOS memakai jendela 60 detik.

Tips di Pi 5:
- Pakai webcam USB yang mendukung **MJPG** (dipakai program secara default).
- Kalau berat, turunkan resolusi di `config.json` ke `320×240`.
- Pastikan pendingin/heatsink terpasang bila dipakai lama.

---

## Menganalisis rekaman video

Selain webcam langsung, program bisa memproses berkas video — berguna untuk
menguji ulang kasus yang sama berkali-kali sambil menyetel ambang.

```bash
./run.sh --sumber example.mp4 --kalibrasi 8 --tanpa-jendela \
         --rekam hasil/example_anotasi.webm
```

Untuk sumber berkas, waktu diambil dari **timeline video**, bukan jam dinding,
sehingga durasi kalibrasi dan jendela PERCLOS tetap benar walau pemrosesan
berjalan lebih cepat daripada waktu nyata. Efek cermin dimatikan otomatis.

Codec rekaman mengikuti ekstensi berkas: `.webm` (VP8) bisa langsung diputar
peramban tanpa memasang codec apa pun, `.mp4` memakai MPEG-4 Part 2 karena
wheel OpenCV tidak membawa encoder H.264.

Di akhir sesi dicetak ringkasan: jumlah kedipan, jumlah menguap, dan daftar
periode KANTUK lengkap dengan rentang waktu serta alasannya.

```
Frame diproses  : 1781
Kedipan         : 19
Menguap         : 2
Periode KANTUK  : 4
  1. 00:11.67 - 00:13.73 (2.1 detik) : sedang menguap
  2. 00:15.10 - 00:16.13 (1.0 detik) : mata terpejam 1.2 detik
  3. 00:49.27 - 00:51.80 (2.5 detik) : sedang menguap
  4. 01:00.00 - 01:00.40 (0.4 detik) : mata terpejam 1.2 detik
```

---

## Pemakaian

```bash
./run.sh                      # webcam Logitech yang sedang tertancap
./run.sh --langsung           # lewati layar siaga, sistem langsung menyala
./run.sh --tanpa-suara        # matikan asisten suara (visual saja)
./run.sh --sumber 1           # dahulukan index tertentu (tetap harus Logitech)
./run.sh --merek ''           # terima kamera merek apa pun
./run.sh --sumber video.mp4   # uji dari file video
./run.sh --kalibrasi 6        # kalibrasi 6 detik
./run.sh --tanpa-jendela      # headless, status dicetak ke terminal
./run.sh --debug              # tampilkan seluruh 478 landmark
./run.sh --verbose            # tampilkan pesan bawaan OpenCV/MediaPipe
```

Program hanya mau memakai **webcam Logitech yang sedang tertancap**. Node
`/dev/videoN` disaring lewat `idVendor` USB (`046d`), bukan lewat namanya —
C270 mendaftar sebagai `C270 HD WEBCAM` saja, tanpa kata "Logitech". Kalau
webcam itu tidak ada, program berhenti dengan pesan yang jelas dan **tidak**
diam-diam beralih ke kamera bawaan laptop, supaya hasil deteksi selalu berasal
dari kamera yang sama. Nomor index di `config.json` sekadar pilihan pertama:
kalau bergeser setelah cabut-tancap, node Logitech lain dipakai otomatis.
Merek lain bisa diterima lewat `--merek` atau kunci `kamera.merek` di
`config.json` (isi nama merek, `idVendor`, potongan nama perangkat, atau
kosongkan untuk menerima semua). Analisis berkas video tidak terpengaruh
penyaringan ini.

Tombol:

| Tombol | Fungsi |
|---|---|
| `spasi` | nyalakan sistem dari layar SIAGA |
| `q` / `Esc` | keluar |
| `c` | kalibrasi ulang |
| `d` | tampilkan/sembunyikan landmark |

Di mode headless tombol dibaca langsung dari terminal (tanpa perlu Enter).
Kalau stdin bukan terminal — mis. dijalankan systemd atau keluarannya
dialihkan ke berkas — SPASI mustahil ditekan, jadi sistem langsung menyala
sendiri, sama seperti `--langsung`.

Bingung webcam mana yang aktif, atau gambar terlihat rusak:

```bash
.venv/bin/python tools/cek_kamera.py   # ukur FPS nyata + frame robek tiap format
.venv/bin/python tools/cek_suara.py    # dengarkan semua pesan asisten
.venv/bin/python tools/uji_logika.py   # uji penilaian kantuk + asisten (tanpa kamera)
```

`cek_kamera.py` mencoba tiap kombinasi format/resolusi lalu menyarankan yang
paling bersih, lengkap dengan potongan `config.json` yang tinggal disalin.

---

## Konfigurasi

Semua ambang ada di `config.json` — bisa diubah tanpa menyentuh kode.

```jsonc
{
  "kamera": {
    "sumber": "2",            // index webcam atau path file video
    "merek": "logitech",      // hanya kamera merek ini; "" = terima semua
    "lebar": 640, "tinggi": 480, "fps": 30,
    "fourcc": "MJPG",         // "MJPG" | "YUYV" | "" (biarkan driver)
    "flip_horizontal": true   // tampilan cermin
  },
  "ambang": {
    "rasio_mata_tertutup": 0.62,     // EAR < 62% baseline = terpejam
    "durasi_terpejam_detik": 1.2,    // terpejam selama ini -> KANTUK
    "perclos_window_detik": 60.0,
    "perclos_kantuk": 0.28,          // >28% -> KANTUK
    "perclos_min_rentang": 30.0,     // PERCLOS dipercaya setelah 30 detik
    "durasi_kedip_maks": 0.5,        // batas atas durasi satu kedipan
    "mar_menguap": 0.50,             // ambang MUTLAK MAR untuk menganga
    "mar_margin_baseline": 0.30,     // jarak minimum dari baseline tiap orang
    "durasi_menguap_detik": 0.9,
    "kantuk_saat_menguap": true,     // KANTUK selama menguap berlangsung
    "menguap_per_menit_kantuk": 0    // 0 = aturan laju menguap dimatikan
  },
  "suara": {
    "aktif": true,
    "voice": "gadis",                // "gadis" (perempuan) | "ardi" (laki-laki)
    "folder": "suara",               // tempat berkas <pesan>-<voice>.wav
    "terpejam_detik": 3.0,           // terpejam selama ini -> bersuara
    "menguap_detik": 2.0,            // menguap selama ini -> bersuara
    "wajah_hilang_detik": 3.0,       // wajah hilang selama ini -> menuntun
    "jeda_ulang_detik": 5.0,         // pesan sama paling cepat diulang
    "pemutar": ""                    // kosong = deteksi otomatis (pw-play/aplay/...)
  },
  "kalibrasi_detik": 4.0,
  "mati_tanpa_wajah_detik": 60.0,    // wajah hilang selama ini -> sistem mati
  "tampilkan_jendela": true
}
```

**Terlalu sering false alarm?** Naikkan `durasi_terpejam_detik` (mis. 1.5) atau
turunkan `rasio_mata_tertutup` (mis. 0.55).
**Kurang sensitif?** Lakukan sebaliknya.

**Mau alarm menguap bertahan lebih lama?** Isi `menguap_per_menit_kantuk`
dengan angka > 0 (mis. 2). Status KANTUK lalu bertahan selama menguap masih
masuk hitungan 60 detik terakhir — alarm ikut menyala walau mulut sudah
tertutup dan mata sudah segar. Default-nya 0 (mati) karena perilaku itu
terasa mengganggu saat diuji pada rekaman nyata.

---

## Kalau hasilnya tidak bagus

| Gejala | Penyebab & solusi |
|---|---|
| Gambar tampak **robek**, tersusun dari beberapa potongan | Webcam kehabisan bandwidth USB. Jalankan `tools/cek_kamera.py`, lalu pakai format/resolusi yang disarankan (biasanya MJPG, atau turun ke 320×240). Pada pengujian di sini YUYV 640×480 merobek 21 dari 30 frame, MJPG hanya 4. |
| Banyak baris `Corrupt JPEG data` di terminal | Sama seperti di atas, tapi versi MJPG — sebagian data frame hilang. Program tetap jalan; ganti ke `"fourcc": "YUYV"` bila mengganggu. |
| Wajah sering tidak terdeteksi | Cahaya kurang, wajah terlalu jauh/miring, atau frame robek. Pastikan wajah menghadap kamera dan cukup terang. |
| **KANTUK** muncul padahal melek | Baseline terlanjur diambil saat mata setengah menutup. Tekan `c` untuk kalibrasi ulang sambil menatap kamera. |
| FPS rendah padahal CPU santai | Batasnya di webcam, bukan program (inferensi hanya ±11 ms). Cek dengan `tools/cek_kamera.py`. |
| **Jendela terbuka sebentar lalu mati**, muncul `VIDIOC_REQBUFS: errno=19 (No such device)` | Webcam lepas dari bus USB. Lihat bagian di bawah. |
| Tidak ada suara sama sekali | Jalankan `tools/cek_suara.py`. Baris `Suara :` saat program mulai menyebut sumber dan pemutarnya; kalau tertulis "TIDAK ADA pemutar suara", pasang `pw-play`/`paplay`/`aplay`, atau tulis pemutar pilihan Anda di `suara.pemutar`. |
| Suaranya robotik | Berkas WAV di `suara/` tidak ketemu sehingga jatuh ke TTS sistem. Cek `folder`/`voice` di `config.json`, atau rekam ulang dengan `tools/buat_suara.py`. |
| Asisten terlalu cerewet | Naikkan `suara.terpejam_detik`/`menguap_detik`, atau perbesar `jeda_ulang_detik`. Matikan sepenuhnya dengan `--tanpa-suara`. |
| Sistem mati sendiri padahal masih dipakai | Wajah tidak terlihat >60 detik (kamera bergeser, terlalu gelap). Perbesar `mati_tanpa_wajah_detik`, atau perbaiki posisi kamera. |
| `Kamera logitech tidak terpasang` | Webcam Logitech-nya memang tidak sedang tertancap — program sengaja berhenti, bukan diam-diam pindah ke kamera bawaan laptop. Tancapkan webcamnya, atau jalankan dengan `--merek ''` bila memang ingin memakai kamera lain. |
| `Kamera '0' tidak bisa dibuka` padahal tadi jalan | Nomor `/dev/videoN` bergeser setelah kamera lepas-sambung. Program sudah menyapu node Logitech yang lain secara otomatis; kalau tetap gagal, kameranya memang sedang tidak ada di sistem. |

### Webcam lepas-sambung sendiri (USB autosuspend)

Gejala di log kernel (`journalctl -k | tail`):

```
usb 1-4: USB disconnect, device number 6
uvcvideo 1-4:1.1: Failed to resubmit video URB (-19).
usb 1-4: new high-speed USB device number 7 using xhci_hcd
```

Kernel menidurkan kamera setelah 2 detik menganggur, lalu sebagian kamera —
termasuk kamera internal laptop uji (SunplusIT `04f2:b71f`) — tidak bangun
dengan benar dan malah lepas dari bus. Perbaikannya mematikan autosuspend
untuk perangkat itu:

```bash
sudo ./tools/perbaiki_kamera_usb.sh              # berlaku sampai reboot
sudo ./tools/perbaiki_kamera_usb.sh --permanen   # + aturan udev, tetap setelah reboot
```

Dari sisi program, kalau aliran frame terputus di tengah jalan, kamera
disambungkan ulang otomatis (termasuk bila nomor `/dev/videoN`-nya berubah)
tanpa kehilangan hasil kalibrasi maupun hitungan PERCLOS.

---

## Struktur project

```
deteksi-kantuk/
├── src/
│   ├── main.py       # mesin keadaan SIAGA -> KALIBRASI -> MONITOR
│   ├── config.py     # dataclass konfigurasi + pembaca config.json
│   ├── kamera.py     # pilih webcam Logitech (V4L2, MJPG) + penanganan galat
│   ├── deteksi.py    # MediaPipe Face Mesh -> EAR & MAR
│   ├── metrik.py     # kalibrasi, PERCLOS, hitung kedip & menguap, level kantuk
│   ├── tampilan.py   # overlay OpenCV (layar siaga, kontur, panel metrik, banner)
│   ├── suara.py      # asisten suara: pesan, antrean, pemutar WAV/TTS cadangan
│   ├── tombol.py     # baca tombol dari terminal untuk mode headless
│   └── senyap.py     # meredam pesan bawaan OpenCV/MediaPipe/libjpeg
├── suara/            # berkas WAV pesan asisten (gadis & ardi)
├── tools/
│   ├── cek_kamera.py            # ukur FPS nyata & frame robek tiap format
│   ├── cek_suara.py             # putar tiap pesan asisten untuk uji speaker
│   ├── buat_suara.py            # rekam ulang pesan dengan TTS neural (butuh internet)
│   ├── uji_logika.py            # uji penilaian kantuk + asisten (frame sintetis)
│   ├── siapkan_raspi.sh         # siapkan kartu SD Pi: user, SSH, WiFi (headless)
│   └── perbaiki_kamera_usb.sh   # matikan USB autosuspend (butuh sudo)
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
