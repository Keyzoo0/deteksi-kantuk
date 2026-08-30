"""Utilitas: cek webcam mana yang layak dipakai, dan format apa yang paling bersih.

Selain memastikan kamera bisa dibuka, skrip ini mengukur dua hal yang sering
jadi biang deteksi buruk:

* **FPS nyata** -- bukan angka yang diklaim driver.
* **Frame robek** -- webcam USB yang kehabisan bandwidth mengirim frame
  setengah jadi (gambar tampak tersusun dari beberapa potongan waktu).
  Frame seperti ini membuat landmark wajah gagal terdeteksi.

Jalankan: .venv/bin/python tools/cek_kamera.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.kamera import daftar_perangkat            # noqa: E402

FORMAT = ("MJPG", "YUYV")
RESOLUSI = ((640, 480), (320, 240))


def baris_jahitan(frame: np.ndarray, ambang: int = 28) -> int:
    """Jumlah baris dengan lompatan kecerahan mencolok -- penanda frame robek."""
    abu = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.int16)
    beda = np.abs(np.diff(abu, axis=0)).mean(axis=1)
    return int((beda > ambang).sum())


def uji_format(idx: int, fourcc: str, lebar: int, tinggi: int,
               jumlah: int = 30) -> tuple[float, int, int] | None:
    cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, lebar)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, tinggi)
    cap.set(cv2.CAP_PROP_FPS, 30)
    for _ in range(10):                      # buang frame pemanasan
        cap.read()

    n = robek = 0
    t0 = time.monotonic()
    while n < jumlah and time.monotonic() - t0 < 10:
        ok, frame = cap.read()
        if not ok:
            continue
        n += 1
        if baris_jahitan(frame) > 2:
            robek += 1
    durasi = time.monotonic() - t0
    cap.release()
    return (n / durasi if durasi else 0.0), robek, n


def main() -> int:
    perangkat = daftar_perangkat()
    print("Perangkat video:")
    for p in perangkat:
        print(f"  {p.label()}{'  <- logitech' if p.cocok('logitech') else ''}")
    if not perangkat:
        print("  (tidak ada)")

    terbaik: tuple[float, int, str, int, int] | None = None
    for p in perangkat:
        idx = p.index
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        siap = cap.isOpened() and cap.read()[0]
        cap.release()
        if not siap:
            print(f"\nindex {idx}: tidak mengirim gambar (lewati)")
            continue

        print(f"\nindex {idx} ({p.nama or p.produk or '-'}):")
        print(f"  {'format':<14} {'fps nyata':>10} {'frame robek':>13}")
        for lebar, tinggi in RESOLUSI:
            for fourcc in FORMAT:
                hasil = uji_format(idx, fourcc, lebar, tinggi)
                if hasil is None:
                    continue
                fps, robek, n = hasil
                nama = f"{fourcc} {lebar}x{tinggi}"
                print(f"  {nama:<14} {fps:>9.1f}  {robek:>6}/{n:<6}")
                # Skor: utamakan frame utuh, lalu resolusi, lalu fps.
                skor = (1 - robek / max(1, n)) * 100 + (lebar * tinggi) / 20000 + fps / 10
                if terbaik is None or skor > terbaik[0]:
                    terbaik = (skor, idx, fourcc, lebar, tinggi)

    print("-" * 46)
    if terbaik is None:
        print("Tidak ada kamera yang siap dipakai.")
        return 1

    _, idx, fourcc, lebar, tinggi = terbaik
    print(f"Saran: kamera index {idx}, format {fourcc}, resolusi {lebar}x{tinggi}")
    print("Setel di config.json -> kamera: "
          f'{{"sumber": "{idx}", "lebar": {lebar}, "tinggi": {tinggi}, "fourcc": "{fourcc}"}}')
    print(f"Atau jalankan langsung: ./run.sh --sumber {idx}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
