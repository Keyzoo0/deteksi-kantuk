#!/usr/bin/env bash
# Sambungkan ulang speaker Bluetooth secara otomatis -- baik saat Pi baru
# hidup maupun kalau putus di tengah jalan.
#
# BlueZ tidak selalu menyambungkan ulang sendiri begitu perangkat kembali
# dalam jangkauan (mis. kepala pengendara sempat menjauh dari alat). Alat ini
# bisu tanpa layar, jadi speaker putus tanpa reconnect otomatis sama artinya
# dengan alarm tidak pernah terdengar sama sekali.
#
# Dijalankan sebagai layanan PENGGUNA (bukan sistem): audio Bluetooth lewat
# PipeWire hidup di sesi pengguna, alasan yang sama dengan kenapa
# deteksi-kantuk.service ada di systemd --user, bukan systemd sistem.
set -u

MAC=84:AC:60:4E:61:5E
JEDA=15

tersambung() {
  bluetoothctl info "$MAC" 2>/dev/null | grep -q "Connected: yes"
}

while true; do
  tersambung || bluetoothctl connect "$MAC" >/dev/null 2>&1
  sleep "$JEDA"
done
