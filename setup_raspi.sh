#!/usr/bin/env bash
# Penyiapan di Raspberry Pi (Raspberry Pi OS Bookworm/Trixie, Pi 4 atau Pi 5).
#
# Soal versi Python: MediaPipe 0.10.x hanya menyediakan wheel sampai Python
# 3.12, sedangkan Raspberry Pi OS Trixie membawa Python 3.13. Untungnya
# MediaPipe 1.x menerbitkan wheel aarch64 bertanda "py3-none" yang tidak
# terikat versi, sehingga Python bawaan sistem tetap bisa dipakai. Kalau
# ternyata gagal, skrip ini otomatis mundur ke Python 3.12 lewat `uv` --
# dipasang ke folder pengguna, tanpa sudo dan tanpa mengubah Python sistem.
set -euo pipefail
cd "$(dirname "$0")"

echo ">> Memasang paket sistem (butuh sudo)..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev libgl1 libglib2.0-0 v4l-utils \
    alsa-utils python3-gpiozero python3-lgpio

# Tombol "tahan 8 detik" harus bisa mematikan Pi tanpa sandi: alat ini dipakai
# tanpa monitor maupun keyboard, dan mencabut daya begitu saja merusak kartu SD.
echo ">> Memberi izin poweroff/reboot tanpa sandi untuk $USER..."
printf '%s ALL=(ALL) NOPASSWD: /sbin/poweroff, /sbin/reboot, /usr/sbin/poweroff, /usr/sbin/reboot\n' \
    "$USER" | sudo tee "/etc/sudoers.d/020_${USER}-poweroff" >/dev/null
sudo chmod 440 "/etc/sudoers.d/020_${USER}-poweroff"

# gpiozero + lgpio tidak bisa dipasang lewat pip (wheel lgpio gagal dibangun
# tanpa pustaka C-nya), tetapi Raspberry Pi OS sudah membawanya sebagai paket
# sistem. Modulnya ditautkan ke venv supaya tetap terpakai tanpa
# --system-site-packages yang ikut menarik paket lain.
tautkan_gpio() {
  local sp
  sp=$(.venv/bin/python -c "import site; print(site.getsitepackages()[0])")
  for m in gpiozero colorzero lgpio.py; do
    [ -e "/usr/lib/python3/dist-packages/$m" ] && ln -sf "/usr/lib/python3/dist-packages/$m" "$sp/"
  done
  for so in /usr/lib/python3/dist-packages/_lgpio*.so; do
    [ -e "$so" ] && ln -sf "$so" "$sp/"
  done
}

# --- pilih interpreter -------------------------------------------------------
PY=""
for kandidat in python3.12 python3.11 python3.10 python3.9 python3; do
  if command -v "$kandidat" >/dev/null 2>&1; then PY="$(command -v "$kandidat")"; break; fi
done
[ -n "$PY" ] || { echo "Python 3 tidak ditemukan." >&2; exit 1; }

pasang() {                     # $1 = interpreter yang dipakai
  rm -rf .venv
  if command -v uv >/dev/null 2>&1; then
    uv venv --python "$1" .venv
    uv pip install --python .venv/bin/python -r requirements.txt
  else
    "$1" -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
  fi
}

echo ">> Interpreter: $PY ($("$PY" --version))"
if ! pasang "$PY" || ! .venv/bin/python -c "import cv2, mediapipe" 2>/dev/null; then
  echo ""
  echo ">> Gagal dengan $PY. Menyiapkan Python 3.12 lewat uv sebagai cadangan..."
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  uv python install 3.12
  pasang "$(uv python find 3.12)"
fi

tautkan_gpio
echo ""
.venv/bin/python -c "import cv2, mediapipe, sys; print('Python', sys.version.split()[0], '| OpenCV', cv2.__version__, '| MediaPipe', mediapipe.__version__)"
echo ">> Mengunduh model face_landmarker (sekali saja, ~3,8 MB)..."
.venv/bin/python -c "from src.deteksi import pastikan_model; pastikan_model()"

echo ">> Kamera yang terdeteksi:"
v4l2-ctl --list-devices 2>/dev/null || true
echo ">> Keluaran audio yang terdeteksi:"
aplay -l 2>/dev/null | grep -E "^card" || echo "   (tidak ada; asisten suara butuh speaker/dongle audio USB)"

echo ""
echo ">> Selesai. Jalankan dengan: ./run.sh"
