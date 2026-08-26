#!/usr/bin/env bash
# Matikan USB autosuspend untuk webcam.
#
# Sebagian kamera (terutama kamera internal laptop) tidak tahan disuspend:
# begitu kernel menidurkannya, perangkat lepas dari bus lalu muncul lagi
# dengan nomor /dev/videoN yang berbeda. Gejalanya di log kernel:
#
#   usb 1-4: USB disconnect, device number 6
#   uvcvideo 1-4:1.1: Failed to resubmit video URB (-19).
#
# Pemakaian:
#   sudo ./tools/perbaiki_kamera_usb.sh              # berlaku sampai reboot
#   sudo ./tools/perbaiki_kamera_usb.sh --permanen   # + pasang aturan udev
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Perlu hak root. Jalankan: sudo $0 $*" >&2
  exit 1
fi

PERMANEN=0
[ "${1:-}" = "--permanen" ] && PERMANEN=1

ketemu=0
for dev in /sys/bus/usb/devices/*/; do
  [ -e "$dev/idVendor" ] || continue
  # Hanya perangkat yang punya antarmuka kelas video (UVC = 0x0e).
  if ! grep -qs "^0e" "$dev"/*/bInterfaceClass 2>/dev/null; then
    continue
  fi
  vid=$(cat "$dev/idVendor")
  pid=$(cat "$dev/idProduct")
  nama=$(cat "$dev/product" 2>/dev/null || echo "kamera")
  ketemu=1

  echo "Kamera : $nama ($vid:$pid) di $(basename "$dev")"
  echo "  status sebelum : $(cat "$dev/power/control") / $(cat "$dev/power/runtime_status")"
  echo on > "$dev/power/control"
  echo "  status sesudah : $(cat "$dev/power/control") / $(cat "$dev/power/runtime_status")"

  if [ "$PERMANEN" -eq 1 ]; then
    aturan=/etc/udev/rules.d/50-webcam-no-autosuspend.rules
    baris="ACTION==\"add\", SUBSYSTEM==\"usb\", ATTR{idVendor}==\"$vid\", ATTR{idProduct}==\"$pid\", TEST==\"power/control\", ATTR{power/control}=\"on\""
    touch "$aturan"
    if grep -qF "$vid\", ATTR{idProduct}==\"$pid" "$aturan"; then
      echo "  aturan udev    : sudah ada"
    else
      echo "$baris" >> "$aturan"
      echo "  aturan udev    : ditambahkan ke $aturan"
    fi
  fi
done

if [ "$ketemu" -eq 0 ]; then
  echo "Tidak menemukan perangkat kamera USB (kelas UVC)." >&2
  exit 1
fi

if [ "$PERMANEN" -eq 1 ]; then
  udevadm control --reload-rules && udevadm trigger
  echo "Aturan udev dimuat ulang -- setelan bertahan setelah reboot."
else
  echo "Selesai (berlaku sampai reboot). Tambahkan --permanen agar menetap."
fi
