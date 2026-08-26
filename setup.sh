#!/usr/bin/env bash
# Menyiapkan virtualenv + dependensi.
#
# MediaPipe hanya menyediakan wheel untuk Python 3.9-3.12. Skrip ini mencari
# interpreter yang cocok di sistem; kalau tidak ada (mis. Ubuntu 26.04 yang
# hanya punya Python 3.14), Python 3.12 diunduh lewat `uv` ke folder pengguna
# tanpa perlu sudo dan tanpa mengubah Python bawaan sistem.
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for kandidat in python3.12 python3.11 python3.10 python3.9; do
  if command -v "$kandidat" >/dev/null 2>&1; then PY="$kandidat"; break; fi
done

if [ -z "$PY" ]; then
  echo ">> Python 3.9-3.12 tidak ditemukan, menyiapkan Python 3.12 via uv..."
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  uv python install 3.12
  PY="$(uv python find 3.12)"
fi

echo ">> Interpreter: $PY ($("$PY" --version))"
rm -rf .venv
if command -v uv >/dev/null 2>&1; then
  uv venv --python "$PY" .venv
  VIRTUAL_ENV=.venv uv pip install -r requirements.txt
else
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

echo ""
.venv/bin/python -c "import cv2, mediapipe; print('OpenCV', cv2.__version__, '| MediaPipe', mediapipe.__version__)"
echo ">> Selesai. Jalankan dengan: ./run.sh"
