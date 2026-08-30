---
description: Muat konteks proyek deteksi-kantuk (remote control dari Raspberry Pi)
---

Anda berjalan di **Raspberry Pi 5** yang menjadi otak alat deteksi kantuk
pengendara motor. Sesi ini dipakai pemilik untuk mengendalikan alat dari jauh.

Lakukan ini sekarang, ringkas:

1. Baca `CLAUDE.md` di akar proyek — di situ ada seluruh konteks perangkat
   keras, jaringan, keputusan rancangan, dan status pengerjaan.
2. Laporkan keadaan alat dalam beberapa baris:
   - `systemctl --user is-active deteksi-kantuk` (layanan monitoring)
   - `ip -4 route | grep default` dan `ping -c1 -W2 8.8.8.8` (internet)
   - `git -C ~/deteksi-kantuk status --short` dan `git log --oneline -1`
3. Tunggu perintah pemilik. Untuk mengubah tampilan web, ingat: bangun di
   folder `web/` dengan `npm run build`, lalu salin `web/dist` — TAPI Pi ini
   mungkin tidak punya Node; kalau tidak ada, katakan dan minta build dari
   laptop.

Jangan menjalankan hal berisiko (reboot, matikan, ganti jaringan, `git push`)
tanpa diminta eksplisit oleh pemilik pada sesi ini.
