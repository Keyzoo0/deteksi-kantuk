#!/usr/bin/env bash
# Penyiapan khusus Raspberry Pi 5 (Raspberry Pi OS Bookworm, Python 3.11).
#
# MediaPipe punya wheel aarch64 untuk Python 3.11, jadi tidak perlu compile.
# Paket sistem di bawah dibutuhkan OpenCV untuk membuka jendela & baca webcam.
set -euo pipefail
cd "$(dirname "$0")"

echo ">> Memasang paket sistem (butuh sudo)..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev libgl1 libglib2.0-0 v4l-utils

echo ">> Membuat virtualenv..."
rm -rf .venv
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo ""
.venv/bin/python -c "import cv2, mediapipe; print('OpenCV', cv2.__version__, '| MediaPipe', mediapipe.__version__)"
echo ">> Cek webcam terdeteksi:"
v4l2-ctl --list-devices || true
echo ">> Selesai. Jalankan dengan: ./run.sh"
