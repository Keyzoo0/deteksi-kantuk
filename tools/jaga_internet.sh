#!/usr/bin/env bash
# Pindah jalur internet secara otomatis mengikuti kondisi modem USB.
#
# Dipasang di motor: Pi selalu menyalakan AP WiFi "deteksikantuk" supaya HP
# pengemudi ikut dapat internet dari modem. Masalahnya radio WiFi Pi hanya
# satu: tidak bisa jadi AP DAN klien sekaligus. Jadi saat modem hilang/mati,
# jaringannya dialihkan -- AP dimatikan dan wlan0 menjadi klien ke SSID
# cadangan (HUAWEI-WINKS) supaya alat sendiri masih bisa mengirim notifikasi.
#
# Keadaan dicek berkala dan hanya diubah kalau benar-benar berbeda, supaya
# NetworkManager tidak diombang-ambingkan perintah yang sia-sia.
#
# Dijalankan sebagai layanan sistem (root): memindahkan koneksi NM butuh
# hak root dan harus tetap hidup walau tidak ada yang login. Lihat
# jaga-internet.service.
set -u

AP=hotspot-pi
KLIEN=preconfigured
JEDA=15

# Nama antarmuka modem: Qualcomm yang dipakai muncul sebagai usb0, tapi
# modem RNDIS/QMI lain bisa wwan0 dst. Apa pun bentuknya, dikenali dari
# awalan nama, bukan dari isi bus USB. Berarti "ada" cukup -- mencabut modem
# membuat antarmukanya lenyap dari /sys/class/net, tanpa perlu menebak-nebak
# state NM (unknown/up/down tergantung jenis antarmukanya).
modem_hidup() {
  for ant in /sys/class/net/usb* /sys/class/net/wwan*; do
    [ -e "$ant" ] || continue
    # Ada antarmukanya saja TIDAK cukup. Modem yang jatuh ke mode diagnostik
    # (mis. 05c6:9091 -> wwan0) tetap memunculkan antarmuka, tetapi tanpa
    # alamat IP dan tanpa internet sama sekali. Kalau itu dianggap "hidup",
    # Pi bertahan di mode AP dan tidak pernah pindah ke WiFi cadangan --
    # alat berakhir tanpa internet sama sekali. Jadi yang dipakai sebagai
    # bukti adalah adanya alamat IPv4, bukan sekadar keberadaan antarmuka.
    ip -4 addr show "${ant##*/}" 2>/dev/null | grep -q "inet " && return 0
  done
  return 1
}

koneksi_aktif() {   # 3 detik gaya NetworkManager, tanpa mengubah keadaan
  nmcli -t -f NAME connection show --active 2>/dev/null | grep -qx "$1"
}

# `nmcli con up` menunggu sampai koneksi benar-benar aktif -- bawaannya 90
# detik. Selama itu loop di bawah berhenti memantau, sehingga modem yang sudah
# kembali hidup baru disadari beberapa menit kemudian. Batas tunggu dipendekkan
# supaya pemantauan cepat berjalan lagi; kalau koneksinya belum jadi, putaran
# berikutnya toh akan mencoba lagi.
TUNGGU=20

atur() {            # $1 = ap | klien
  local nama
  if [ "$1" = ap ]; then
    nmcli con mod "$AP" connection.autoconnect yes >/dev/null
    nmcli --wait "$TUNGGU" con up "$AP" >/dev/null 2>&1
    nama="$KLIEN"
  else
    nmcli con mod "$AP" connection.autoconnect no >/dev/null
    if koneksi_aktif "$AP"; then
      nmcli --wait 5 con down "$AP" >/dev/null 2>&1
    fi
    nmcli --wait "$TUNGGU" con up "$KLIEN" >/dev/null 2>&1
    nama="$AP"
  fi
  # Koneksi lawan jenisnya (klien saat ap, ap saat klien) dikunci mati supaya
  # permintaan autoconnect NM tidak merebut wlan0 di tengah-tengah.
  koneksi_aktif "$nama" && nmcli --wait 5 con down "$nama" >/dev/null 2>&1
}

sebelumnya=""
calon=""
cocok=0
while true; do
  if modem_hidup; then
    kini="ap"
  else
    kini="klien"
  fi
  # Modem sempat lenyap beberapa detik saat berganti mode USB. Tanpa
  # konfirmasi, satu pembacaan meleset sudah cukup membalik mode dan
  # membuat wlan0 diombang-ambingkan tiap belasan detik. Perubahan baru
  # dieksekusi setelah terbaca sama dua kali berturut-turut.
  if [ "$kini" = "$calon" ]; then
    cocok=$((cocok + 1))
  else
    calon="$kini"
    cocok=1
  fi
  if [ "$kini" != "$sebelumnya" ] && [ "$cocok" -ge 2 ]; then
    atur "$kini"
    if ! koneksi_aktif "$AP" && ! koneksi_aktif "$KLIEN"; then
      # Bila tidak satu pun aktif (mis. HUAWEI-WINKS sedang di luar jangkauan),
      # dicoba ulang diam-diam pada putaran berikutnya tanpa panik.
      :
    fi
    sebelumnya="$kini"
    echo "jaga-internet: beralih ke mode $kini"
  fi
  sleep "$JEDA"
done