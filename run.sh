#!/usr/bin/env bash
# Menjalankan deteksi kantuk memakai virtualenv project.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "Virtualenv belum ada. Jalankan dulu: ./setup.sh" >&2
  exit 1
fi

exec .venv/bin/python -m src.main "$@"
