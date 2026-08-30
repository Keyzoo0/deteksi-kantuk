#!/usr/bin/env bash
# Menyiapkan kartu SD Raspberry Pi OS untuk dipakai TANPA monitor (headless):
# membuat pengguna, menyalakan SSH, dan mengisikan WiFi laptop ini ke Pi.
#
# Jalankan setelah kartu SD hasil Raspberry Pi Imager ditancapkan:
#
#     sudo ./tools/siapkan_raspi.sh
#     sudo ./tools/siapkan_raspi.sh --pengguna haris --sandi 1 --nama-host raspberrypi
#
# Butuh root karena partisi kartu SD dan sandi WiFi di NetworkManager hanya
# bisa dibaca root. Sandi WiFi tidak pernah ditampilkan di layar.
set -euo pipefail

PENGGUNA="haris"
SANDI="1"
NAMA_HOST="raspberrypi"
SSID=""
PSK=""
NEGARA=""
KUNCI=""
ZONA="Asia/Jakarta"
BOOT_SIAP=""
ROOT_SIAP=""

pesan() { printf '%s\n' "$*"; }
galat() { printf '\nGALAT: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --pengguna)  PENGGUNA="$2"; shift 2 ;;
    --sandi)     SANDI="$2"; shift 2 ;;
    --nama-host) NAMA_HOST="$2"; shift 2 ;;
    --ssid)      SSID="$2"; shift 2 ;;
    --psk)       PSK="$2"; shift 2 ;;
    --negara)    NEGARA="$2"; shift 2 ;;
    --kunci)     KUNCI="$2"; shift 2 ;;
    --boot)      BOOT_SIAP="$2"; shift 2 ;;   # partisi sudah terpasang sendiri
    --root)      ROOT_SIAP="$2"; shift 2 ;;
    --tanpa-kunci) KUNCI="-"; shift ;;
    -h|--help)   sed -n '2,12p' "$0"; exit 0 ;;
    *)           galat "argumen tidak dikenal: $1" ;;
  esac
done

[ "$(id -u)" = "0" ] || galat "jalankan dengan sudo: sudo $0"
command -v openssl >/dev/null || galat "butuh openssl untuk membuat hash sandi"

# --- 1. cari partisi kartu SD -----------------------------------------------
# Bila titik pasangnya disebut sendiri (mis. kartu sudah dipasang otomatis oleh
# desktop), pencarian lewat label dilewati.
if [ -n "$BOOT_SIAP" ] || [ -n "$ROOT_SIAP" ]; then
  [ -n "$BOOT_SIAP" ] && [ -n "$ROOT_SIAP" ] || galat "--boot dan --root harus berpasangan."
fi
# Citra Raspberry Pi OS selalu memberi label: FAT "bootfs" (dulu "boot") dan
# ext4 "rootfs". Mencari lewat label jauh lebih aman daripada menebak /dev/sdX.
cari_partisi() {
  local label dev
  for label in "$@"; do
    dev=$(blkid -L "$label" 2>/dev/null || true)
    if [ -n "$dev" ]; then printf '%s' "$dev"; return 0; fi
  done
  return 1
}

if [ -z "$BOOT_SIAP" ]; then
BOOT_DEV=$(cari_partisi bootfs boot) || galat \
  "partisi boot kartu SD tidak ketemu. Tancapkan kartu SD-nya, lalu ulangi.
  Cek dengan: lsblk -o NAME,SIZE,FSTYPE,LABEL"
ROOT_DEV=$(cari_partisi rootfs) || galat "partisi rootfs kartu SD tidak ketemu."

# Pastikan bukan disk sistem yang sedang berjalan.
DISK_SISTEM=$(lsblk -no PKNAME "$(findmnt -no SOURCE / | head -1)" 2>/dev/null | head -1 || true)
DISK_SD=$(lsblk -no PKNAME "$BOOT_DEV" | head -1)
if [ -n "$DISK_SISTEM" ] && [ "$DISK_SISTEM" = "$DISK_SD" ]; then
  galat "partisi yang ketemu ada di disk sistem ($DISK_SD) -- dibatalkan demi keamanan."
fi

pesan "Kartu SD  : boot=$BOOT_DEV  root=$ROOT_DEV (disk /dev/$DISK_SD)"
fi

# --- 2. pasang (mount) kedua partisi ----------------------------------------
LEPAS=()
MNT_HASIL=""
# Hasil ditaruh di variabel global, bukan lewat $( ): substitusi perintah
# berjalan di subshell sehingga daftar partisi yang perlu dilepas akan hilang.
pasang() {                     # $1=perangkat -> isi $MNT_HASIL
  local dev="$1" mnt
  mnt=$(findmnt -no TARGET "$dev" 2>/dev/null | head -1 || true)
  if [ -z "$mnt" ]; then
    mnt=$(mktemp -d /tmp/raspi-XXXX)
    mount "$dev" "$mnt"
    LEPAS+=("$mnt")
  fi
  MNT_HASIL="$mnt"
}
bersihkan() {
  sync
  local m
  for m in "${LEPAS[@]:-}"; do
    if [ -n "$m" ]; then
      umount "$m" 2>/dev/null || true
      rmdir "$m" 2>/dev/null || true
    fi
  done
  return 0                      # jangan sampai status trap menimpa status skrip
}
trap bersihkan EXIT

if [ -n "$BOOT_SIAP" ]; then
  BOOT_MNT="$BOOT_SIAP"; ROOT_MNT="$ROOT_SIAP"
else
  pasang "$BOOT_DEV"; BOOT_MNT="$MNT_HASIL"
  pasang "$ROOT_DEV"; ROOT_MNT="$MNT_HASIL"
fi
[ -f "$BOOT_MNT/config.txt" ] || galat "$BOOT_MNT bukan partisi boot Raspberry Pi."
[ -f "$ROOT_MNT/etc/os-release" ] || galat "$ROOT_MNT bukan rootfs Raspberry Pi."
pesan "OS di kartu: $(sed -n 's/^PRETTY_NAME="\(.*\)"/\1/p' "$ROOT_MNT/etc/os-release")"

# --- 3. WiFi: ambil dari laptop ini bila tidak diberikan --------------------
if [ -z "$SSID" ]; then
  SSID=$(nmcli -t -f NAME,TYPE connection show --active 2>/dev/null \
         | awk -F: '$2=="802-11-wireless"{print $1; exit}')
  [ -n "$SSID" ] || galat "tidak ada WiFi aktif di laptop ini; berikan --ssid dan --psk."
fi
if [ -z "$PSK" ]; then
  PSK=$(nmcli -s -g 802-11-wireless-security.psk connection show "$SSID" 2>/dev/null || true)
  [ -n "$PSK" ] || galat "sandi WiFi '$SSID' tidak terbaca; berikan lewat --psk."
fi
# Kode negara dipakai kernel untuk membuka kanal WiFi yang sah; tanpa ini
# radio WiFi Raspberry Pi OS tetap terkunci (rfkill).
[ -n "$NEGARA" ] || NEGARA=$(iw reg get 2>/dev/null | awk '/country/{print $2; exit}' | tr -d ':')
case "$NEGARA" in ""|00) NEGARA="ID" ;; esac
pesan "WiFi      : SSID '$SSID' (sandi ${#PSK} karakter, tidak ditampilkan), negara $NEGARA"

# --- 4. kunci SSH -----------------------------------------------------------
if [ -z "$KUNCI" ]; then
  PEMILIK=${SUDO_USER:-$USER}
  RUMAH=$(getent passwd "$PEMILIK" | cut -d: -f6)
  for f in "$RUMAH/.ssh/id_ed25519.pub" "$RUMAH/.ssh/id_rsa.pub"; do
    if [ -f "$f" ]; then KUNCI="$f"; break; fi
  done
fi
KUNCI_ISI=""
if [ -n "$KUNCI" ] && [ "$KUNCI" != "-" ] && [ -f "$KUNCI" ]; then
  KUNCI_ISI=$(head -1 "$KUNCI")
  pesan "Kunci SSH : $KUNCI (login tanpa sandi)"
else
  pesan "Kunci SSH : tidak dipasang (login pakai sandi saja)"
fi

HASH=$(openssl passwd -6 "$SANDI")

# --- 5. tulis konfigurasi awal ----------------------------------------------
# Citra baru (Bookworm ke atas) membaca /boot/firmware/custom.toml lewat
# raspberrypi-sys-mods; citra lama memakai userconf.txt + wpa_supplicant.conf.
# Berkas firstrun.sh bawaan Imager dinonaktifkan agar tidak saling menimpa.
if [ -f "$BOOT_MNT/firstrun.sh" ] && ! grep -q "tools/siapkan_raspi.sh" "$BOOT_MNT/firstrun.sh"; then
  mv "$BOOT_MNT/firstrun.sh" "$BOOT_MNT/firstrun.sh.bak"
  sed -i 's| systemd.run=[^ ]*||g; s| systemd.run_success_action=[^ ]*||g; s| systemd.unit=kernel-command-line[^ ]*||g' \
      "$BOOT_MNT/cmdline.txt"
  pesan "Catatan   : firstrun.sh bawaan Imager dinonaktifkan (disimpan .bak)"
fi

# Tiga mekanisme yang mungkin dipahami citra, diperiksa dari yang paling baru:
#   init_config    -> membaca /boot/firmware/custom.toml
#   imager_custom  -> jalur Raspberry Pi Imager: firstrun.sh + systemd.run
#   (tidak ada)    -> jalur klasik userconf.txt + wpa_supplicant.conf
# Keberadaan imager_custom SAJA tidak cukup untuk custom.toml: citra Trixie
# menyediakan imager_custom tanpa init_config, sehingga custom.toml diabaikan
# diam-diam dan Pi ikut boot tanpa pengguna sama sekali.
SYSMODS="$ROOT_MNT/usr/lib/raspberrypi-sys-mods"
kutip() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }

if [ -f "$SYSMODS/init_config" ]; then
  CARA="custom.toml"
  umask 077
  cat > "$BOOT_MNT/custom.toml" <<TOML
# Dibuat oleh tools/siapkan_raspi.sh -- dibaca sekali saat boot pertama.
config_version = 1

[system]
hostname = "$NAMA_HOST"

[user]
name = "$PENGGUNA"
password = "$HASH"
password_encrypted = true

[ssh]
enabled = true
password_authentication = true
$([ -n "$KUNCI_ISI" ] && printf 'authorized_keys = [ "%s" ]' "$KUNCI_ISI")

[wlan]
ssid = "$SSID"
password = "$PSK"
password_encrypted = false
hidden = false
country = "$NEGARA"

[locale]
keymap = "us"
timezone = "$ZONA"
TOML
  umask 022

elif [ -f "$SYSMODS/imager_custom" ]; then
  CARA="firstrun.sh + userconf.txt"
  rm -f "$BOOT_MNT/custom.toml"          # tidak ada pembacanya di citra ini
  # Pengguna dibuat oleh userconfig.service bawaan citra (membaca userconf.txt),
  # terpisah dari firstrun.sh yang jalan di boot minimal sebelum reboot.
  printf '%s:%s\n' "$PENGGUNA" "$HASH" > "$BOOT_MNT/userconf.txt"

  PUNYA_WLAN=no
  grep -q "set_wlan" "$SYSMODS/imager_custom" 2>/dev/null && PUNYA_WLAN=yes
  pesan "Helper    : imager_custom (set_wlan: $PUNYA_WLAN), userconf-pi: $([ -f "$ROOT_MNT/usr/lib/userconf-pi/userconf" ] && echo ada || echo tidak)"

  umask 077
  cat > "$BOOT_MNT/firstrun.sh" <<FIRST
#!/bin/bash
# Dibuat oleh tools/siapkan_raspi.sh -- dijalankan sekali saat boot pertama,
# lalu menghapus dirinya sendiri. Semua perintah di sini berjalan sebagai root
# di dalam sistem Pi yang sudah hidup, jadi helper bawaan citra dipakai lebih
# dulu dan perintah biasa jadi cadangannya.
set +e
IC=/usr/lib/raspberrypi-sys-mods/imager_custom
PENGGUNA=$(kutip "$PENGGUNA")
HASH=$(kutip "$HASH")

# --- nama host ---
if [ -x "\$IC" ]; then
  "\$IC" set_hostname $(kutip "$NAMA_HOST")
else
  echo $(kutip "$NAMA_HOST") > /etc/hostname
  sed -i "s/^127.0.1.1.*/127.0.1.1\t$NAMA_HOST/" /etc/hosts
fi

# --- pengguna ---
# Helper bawaan dicoba lebih dulu, TAPI hasilnya diperiksa: sebagian versi
# userconf hanya bisa mengganti nama pengguna uid 1000 yang sudah ada,
# sedangkan citra ini tidak punya pengguna bawaan sama sekali. Tanpa
# pemeriksaan ini, kegagalannya baru ketahuan saat Pi tidak bisa di-SSH.
if ! getent passwd "\$PENGGUNA" >/dev/null && [ -x /usr/lib/userconf-pi/userconf ]; then
  /usr/lib/userconf-pi/userconf "\$PENGGUNA" "\$HASH"
fi
if ! getent passwd "\$PENGGUNA" >/dev/null; then
  useradd -m -s /bin/bash "\$PENGGUNA"
  echo "\$PENGGUNA:\$HASH" | chpasswd -e
  for g in adm dialout cdrom sudo audio video plugdev games users input render netdev gpio i2c spi lp; do
    getent group "\$g" >/dev/null && usermod -aG "\$g" "\$PENGGUNA"
  done
  # sudo tanpa sandi, seperti pengguna pertama bawaan Raspberry Pi OS
  printf '%s ALL=(ALL) NOPASSWD: ALL\n' "\$PENGGUNA" > "/etc/sudoers.d/010_\$PENGGUNA-nopasswd"
  chmod 440 "/etc/sudoers.d/010_\$PENGGUNA-nopasswd"
fi

# --- kunci SSH langsung ke rumah pengguna ---
# /etc/skel hanya tersalin kalau pengguna dibuat lewat useradd -m; ini
# memastikan kuncinya terpasang lewat jalur mana pun pengguna dibuat.
KUNCI=$(kutip "$KUNCI_ISI")
if [ -n "\$KUNCI" ]; then
  RUMAH=\$(getent passwd "\$PENGGUNA" | cut -d: -f6)
  if [ -n "\$RUMAH" ]; then
    install -d -m 700 "\$RUMAH/.ssh"
    grep -qxF "\$KUNCI" "\$RUMAH/.ssh/authorized_keys" 2>/dev/null || \
        echo "\$KUNCI" >> "\$RUMAH/.ssh/authorized_keys"
    chmod 600 "\$RUMAH/.ssh/authorized_keys"
    chown -R "\$PENGGUNA:\$PENGGUNA" "\$RUMAH/.ssh"
  fi
fi

# --- SSH ---
if [ -x "\$IC" ]; then "\$IC" enable_ssh; else systemctl enable ssh; fi

# --- WiFi ---
if [ -x "\$IC" ] && grep -q set_wlan "\$IC"; then
  "\$IC" set_wlan $(kutip "$SSID") $(kutip "$PSK") $(kutip "$NEGARA")
else
  install -d -m 700 /etc/NetworkManager/system-connections
  BERKAS="/etc/NetworkManager/system-connections/$SSID.nmconnection"
  cat > "\$BERKAS" <<NM
[connection]
id=$SSID
uuid=\$(cat /proc/sys/kernel/random/uuid)
type=wifi
autoconnect=true

[wifi]
mode=infrastructure
ssid=$SSID

[wifi-security]
key-mgmt=wpa-psk
psk=$PSK

[ipv4]
method=auto

[ipv6]
method=auto
NM
  chmod 600 "\$BERKAS"
  command -v raspi-config >/dev/null && raspi-config nonint do_wifi_country $(kutip "$NEGARA")
  command -v rfkill >/dev/null && rfkill unblock wifi
fi

# --- bersih-bersih: hapus diri dan jejaknya di cmdline ---
rm -f /boot/firmware/firstrun.sh /boot/firstrun.sh
sed -i 's| systemd.run=[^ ]*||g; s| systemd.run_success_action=[^ ]*||g; s| systemd.unit=[^ ]*||g' \
    /boot/firmware/cmdline.txt 2>/dev/null || \
sed -i 's| systemd.run=[^ ]*||g; s| systemd.run_success_action=[^ ]*||g; s| systemd.unit=[^ ]*||g' \
    /boot/cmdline.txt 2>/dev/null
exit 0
FIRST
  umask 022
  chmod +x "$BOOT_MNT/firstrun.sh"
  # cmdline.txt harus tetap SATU baris; token lama dibersihkan dulu agar tidak
  # menumpuk bila skrip ini dijalankan dua kali.
  BARIS=$(tr -d '\n' < "$BOOT_MNT/cmdline.txt" \
          | sed 's| systemd.run=[^ ]*||g; s| systemd.run_success_action=[^ ]*||g; s| systemd.unit=[^ ]*||g')
  printf '%s systemd.run=/boot/firmware/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target\n' \
      "$BARIS" > "$BOOT_MNT/cmdline.txt"

else
  CARA="userconf.txt + wpa_supplicant.conf"
  printf '%s:%s\n' "$PENGGUNA" "$HASH" > "$BOOT_MNT/userconf.txt"
  umask 077
  cat > "$BOOT_MNT/wpa_supplicant.conf" <<WPA
country=$NEGARA
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="$SSID"
    psk="$PSK"
    key_mgmt=WPA-PSK
}
WPA
  umask 022
  printf '%s\n' "$NAMA_HOST" > "$ROOT_MNT/etc/hostname"
fi
touch "$BOOT_MNT/ssh"                     # penanda klasik: nyalakan SSH

# Kunci juga dititipkan lewat /etc/skel supaya ikut tersalin ke /home/$PENGGUNA
# saat pengguna dibuat -- jaring pengaman bila [ssh] authorized_keys diabaikan.
if [ -n "$KUNCI_ISI" ]; then
  install -d -m 700 "$ROOT_MNT/etc/skel/.ssh"
  printf '%s\n' "$KUNCI_ISI" > "$ROOT_MNT/etc/skel/.ssh/authorized_keys"
  chmod 600 "$ROOT_MNT/etc/skel/.ssh/authorized_keys"
fi

# Untuk citra lama, SSH dinyalakan langsung di rootfs. Dua hal penting:
#   * pakai "$ROOT_MNT/usr/lib/...", jangan "$ROOT_MNT/lib/...": pada citra
#     baru /lib adalah symlink ABSOLUT ke /usr/lib sehingga pemeriksaannya
#     malah lari ke sistem laptop, bukan ke kartu SD;
#   * lewati bila custom.toml dipakai -- di Debian 13 sshd berjalan lewat
#     socket activation (ssh.socket), dan mengaktifkan ssh.service sendiri
#     bisa bentrok merebut port 22. Biar `raspi-config` di Pi yang mengurus.
if [ "$CARA" != "custom.toml" ] && \
   [ -f "$ROOT_MNT/usr/lib/systemd/system/ssh.service" ]; then
  ln -sf /lib/systemd/system/ssh.service \
     "$ROOT_MNT/etc/systemd/system/multi-user.target.wants/ssh.service"
  rm -f "$ROOT_MNT/etc/ssh/sshd_not_to_be_run"
fi

sync
pesan ""
pesan "SELESAI. Cara: $CARA"
pesan "  Pengguna : $PENGGUNA (sandi: $SANDI)"
pesan "  Nama host: $NAMA_HOST"
pesan ""
pesan "Langkah berikutnya:"
pesan "  1. Lepas kartu SD dengan aman, pasang ke Raspberry Pi, nyalakan."
pesan "  2. Tunggu ~1-2 menit (boot pertama memperluas partisi lalu reboot)."
pesan "  3. Dari laptop ini:  ssh $PENGGUNA@$NAMA_HOST.local"
pesan "     Kalau .local gagal, cari IP-nya:"
pesan "       ip neigh | grep -i 'b8:27:eb\\|dc:a6:32\\|e4:5f:01\\|d8:3a:dd'   # MAC Raspberry Pi"
pesan "       nmap -sn \$(ip -4 route | awk '/default/{print \$3}')/24   # bila nmap ada"
