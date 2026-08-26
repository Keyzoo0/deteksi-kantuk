"""Utilitas: cek webcam mana yang bisa dipakai.

Jalankan: .venv/bin/python tools/cek_kamera.py
"""

from __future__ import annotations

import glob
import sys

import cv2


def main() -> int:
    perangkat = sorted(glob.glob("/dev/video*"))
    print("Perangkat video terdeteksi:", ", ".join(perangkat) or "(tidak ada)")
    print("-" * 58)

    bisa = []
    for path in perangkat:
        idx = int("".join(c for c in path if c.isdigit()))
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            print(f"index {idx:<2} : tidak bisa dibuka")
            cap.release()
            continue
        ok, frame = cap.read()
        if ok and frame is not None:
            h, w = frame.shape[:2]
            fps = cap.get(cv2.CAP_PROP_FPS)
            print(f"index {idx:<2} : OK  {w}x{h} @ {fps:.0f} fps")
            bisa.append(idx)
        else:
            print(f"index {idx:<2} : terbuka tapi tidak mengirim frame")
        cap.release()

    print("-" * 58)
    if bisa:
        print(f"Pakai: ./run.sh --sumber {bisa[0]}")
        return 0
    print("Tidak ada kamera yang siap dipakai.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
