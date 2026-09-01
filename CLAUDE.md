# Konteks proyek deteksi-kantuk

Alat monitoring rasa kantuk pengendara. Target: Raspberry Pi 5 dipasang **di
sepeda motor, menempel di dekat spion**, **tanpa monitor dan tanpa keyboard** —
semua interaksi lewat satu tombol fisik, suara dari perangkat Bluetooth, dan
(rencana) web UI lokal.

Konsekuensi pemasangan di motor yang wajib diingat saat merancang: getaran
tinggi, terkena hujan dan debu, cahaya matahari langsung, wajah pengendara
tertutup helm, tangan memakai sarung tangan dan memegang stang, serta daya
listrik terbatas dari aki motor.

## Perangkat keras terpasang

| Bagian | Detail |
|---|---|
| Papan | Raspberry Pi 5 Model B 8 GB, Raspberry Pi OS 13 (Trixie), Python 3.13.5 |
| Kamera | Logitech C270 USB (`/dev/video0`) — disaring lewat idVendor `046d` |
| Speaker | Bluetooth "BT SPEAKER" `DD:8F:38:E3:98:07`, sink default PipeWire, auto-connect via `bt-speaker.service` |
| GPS | NEO-6M di UART0: GPS TX→pin 15, GPS RX→pin 14. **Pakai `/dev/ttyAMA0` @9600**, bukan `/dev/serial0` (itu debug UART Pi 5). Aktif lewat `dtoverlay=uart0` di `/boot/firmware/config.txt`. Sudah teruji dapat fix. |
| Tombol | Momentary: **GPIO21 (pin 40) ↔ GND (pin 39)**, pull-up internal, active-low. Teruji. |
| LED status | GPIO27 (pin 13) + 330 Ω ke GND (pin 14). Belum dipasang. |

Keputusan pemasangan di motor: audio ke **headset Bluetooth di dalam helm**
(speaker di badan alat kalah oleh angin), tombol dipasang **di stang dekat
jempol kiri** supaya bisa ditekan tanpa melepas genggaman, pemakaian **siang
hari saja** untuk sekarang (kamera biasa buta dalam gelap), dan catu daya dari
**baterai Li-ion + BMS**. BMS memutus daya mendadak saat tegangan habis, tapi
tombol fisik **sengaja tidak bisa mematikan Raspberry Pi itu sendiri**
(keputusan #5) — jadi belum ada cara mematikan Pi dengan aman di lapangan
sebelum baterai kosong selain SSH. Ini kekurangan yang diketahui, belum
diselesaikan (lihat bagian "Belum dikerjakan").

## Akses

- Nama host Pi: **deteksikantuk** → web UI di `http://deteksikantuk.local:8080`
  (mDNS/Avahi, tidak perlu server DNS). `raspberrypi.local` tidak berlaku lagi.
- `ssh raspi` → `10.10.10.2` lewat kabel USB LAN (laptop `10.10.10.1`, profil NM
  `raspi-link` mode *shared*: memberi DHCP + internet ke Pi).
- Jalur WiFi Pi (`192.168.100.x`) kadang hidup kadang tidak; kabel lebih andal.
- Pengguna Pi: `haris`, sandi `1`, sudo pakai sandi (`echo 1 | sudo -S ...`).
- Venv Pi: `~/deteksi-kantuk/.venv` (MediaPipe 1.0.1, OpenCV 5.0.0).
  `gpiozero`/`lgpio` **tidak** bisa di-pip install (gagal build); modul sistem
  ditautkan ke site-packages venv — lihat `setup_raspi.sh`.

## Keputusan rancangan yang sudah disepakati

1. **Tangga alarm 3 tingkat.** L1: suara peringatan berkala. L2 (setelah L1
   bertahan ~10 dtk): alarm menerus, berhenti hanya bila tombol ditekan.
   L3 (10 dtk tanpa tombol): kirim notifikasi + foto ke kerabat, alarm jalan terus.
2. **Setelah L3, atau setelah L2 direset** (kendaraan berhenti / tombol
   ditekan sebelum sempat eskalasi ke L3): kirim pesan penutup + posisi ke
   kerabat, tangga **reset ke L1**, jeda 60 detik. L1 sendirian tetap senyap
   (dianggap belum cukup serius). Tidak ada mode istirahat yang menjeda
   monitoring.
3. **Speaker Bluetooth saja**, tanpa buzzer cadangan. Mitigasi: bila sink BT
   tidak tersambung saat alarm, langsung lompat ke L3 (percuma menunggu tombol
   kalau pengemudi tidak mendengar apa pun).
4. **Notifikasi: Telegram dulu**; WhatsApp Cloud API butuh akun bisnis +
   template disetujui Meta, SMS menyusul setelah modem LTE ada.
5. **Tombol** (aksi dijalankan saat **dilepas**; selagi ditahan hanya keluar
   isyarat):
   - ketuk (<1 dtk) = matikan alarm yang sedang berbunyi
   - tahan 3 dtk ke atas = nyalakan sistem / matikan sistem untuk istirahat
   Menyalakan sistem selalu diawali kalibrasi, jadi mati-nyalakan sekaligus
   berfungsi sebagai kalibrasi ulang -- tidak perlu tombol tersendiri.
   Tombol **sengaja tidak bisa mematikan Raspberry Pi itu sendiri** (dihapus
   1 Sep 2026 atas permintaan pemilik) -- mematikan Pi cuma lewat SSH
   (`sudo poweroff`). Tidak ada overlay `gpio-shutdown` di kernel, jadi tidak
   ada jalan pintas lain di luar kode aplikasi.
6. Alat harus jalan **tanpa over-engineering**: sesedikit mungkin lapisan,
   dependensi, dan berkas. Sampai sekarang dependensi runtime hanya
   mediapipe/opencv/numpy + gpiozero-lgpio bawaan Raspberry Pi OS. Web server
   dan Telegram memakai pustaka standar.
7. **Layanan systemd harus layanan PENGGUNA**, bukan sistem: PipeWire hidup di
   sesi pengguna, dan layanan sistem tanpa XDG_RUNTIME_DIR membuat pw-play
   gagal ("Host is down") sehingga alat bisu tanpa tanda apa pun.

## Status pengerjaan

| Fase | Isi | Status |
|---|---|---|
| 1 | Tombol GPIO + tangga alarm 3 tingkat + suara | selesai, teruji di perangkat |
| 2 | GPS: posisi di riwayat + deteksi kendaraan berhenti | selesai; fix teruji di luar ruangan |
| 3 | Telegram: antrean offline, foto di tingkat 3, daftar kerabat | selesai, teks & foto teruji sampai |
| 4 | Web UI: video, grafik 2 jam, riwayat | selesai |
| 5 | Panel Bluetooth/WiFi/daya + autostart systemd | selesai |
| 6 | Antarmuka Vite + React + shadcn/ui, tab Dashboard & Info | selesai |

Antarmuka ada di `web/` (Vite + React + shadcn/ui + Tailwind v4). Pi hanya
menyajikan `web/dist` yang ikut masuk repo — Pi tidak punya Node. Setelah
mengubah antarmuka: `cd web && npm run build`, lalu
`rsync -az --delete web/dist/ raspi:~/deteksi-kantuk/web/dist/`.

Belum dikerjakan: pemakaian malam hari (butuh kamera NoIR + LED inframerah),
kata sandi untuk web UI, kanal notifikasi selain Telegram (WhatsApp/SMS), dan
cara mematikan Pi dengan aman di lapangan sekarang bahwa tombol tidak lagi
bisa (lihat keputusan #5) -- BMS masih bisa memutus daya mendadak sebelum
baterai benar-benar kosong.

## Perintah yang sering dipakai

```bash
./run.sh --tanpa-jendela                 # jalankan headless
.venv/bin/python tools/uji_logika.py     # uji logika tanpa kamera
.venv/bin/python tools/cek_suara.py      # dengarkan semua pesan
.venv/bin/python tools/cek_kamera.py     # ukur fps & frame robek
.venv/bin/python tools/daftar_kerabat.py # daftarkan penerima Telegram
sudo ./tools/siapkan_raspi.sh            # siapkan kartu SD Pi baru

# di Raspberry Pi
systemctl --user restart deteksi-kantuk
journalctl --user-unit=deteksi-kantuk -f   # catatan: -u tidak jalan lewat SSH
curl -s http://10.10.10.2:8080/data        # keadaan alat dalam JSON
```

Bahasa kode, komentar, dan pesan: **Bahasa Indonesia**. Komentar menjelaskan
*kenapa*, bukan *apa*.


## Remote control dari Raspberry Pi

Claude Code juga terpasang di Pi sendiri (`~/.local/bin/claude`) sebagai sesi
kendali jarak jauh. Layanan pengguna `rc-claude` menjalankannya di dalam tmux
saat boot; pemilik menyambung dengan `tmux attach -t rc`. Command `/rc` memuat
konteks ini.

Jaringan Pi (per Agustus 2026):
- SSH lokal lewat kabel USB LAN: `ssh haris@10.10.10.2` (laptop di 10.10.10.1
  berbagi internet; butuh `ip_forward=1` di laptop — tidak bertahan reboot laptop).
- Internet utama saat dipakai: modem USB (Qualcomm) — jalur `usb0`, permanen,
  otomatis jadi default saat modem ditancap. Modem seluler CGNAT: TIDAK
  terjangkau dari internet tanpa Tailscale/VPN.
- WiFi `deteksikantuk` / `harisdiaz` (modem) autoconnect dimatikan supaya tidak
  berebut subnet dengan USB; nyalakan: `sudo nmcli con up preconfigured`.

git push dari Pi: remote `origin` (GitHub Keyzoo0/deteksi-kantuk). Butuh kunci
SSH Pi terdaftar di GitHub, atau token. Commit selalu di branch, bukan langsung
ke main tanpa alasan.
