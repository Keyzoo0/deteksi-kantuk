"""Program utama deteksi rasa kantuk (mata + mulut) berbasis webcam.

Alur:
    1. Buka webcam.
    2. Kalibrasi beberapa detik -> dapat baseline EAR & MAR pengguna.
    3. Loop: ukur mata/mulut tiap frame, nilai kantuk, tampilkan AMAN/KANTUK.

Jalankan:  python -m src.main            (dari folder project)
Tombol  :  q keluar | c kalibrasi ulang | d tampilkan landmark
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

from .config import Config
from .deteksi import DetektorWajah
from .kamera import buka_kamera, info_kamera
from .metrik import KANTUK, Kalibrator, PenilaiKantuk, Status
from .tampilan import gambar_kalibrasi, gambar_overlay

AKAR = Path(__file__).resolve().parent.parent


def argumen() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="deteksi-kantuk",
        description="Deteksi rasa kantuk dari mata (EAR/PERCLOS) dan mulut (menguap).",
    )
    p.add_argument("--config", default=str(AKAR / "config.json"),
                   help="berkas konfigurasi JSON (default: config.json)")
    p.add_argument("--sumber", help="index webcam (0/1) atau path file video")
    p.add_argument("--kalibrasi", type=float, help="durasi kalibrasi dalam detik")
    p.add_argument("--tanpa-jendela", action="store_true",
                   help="mode headless: status dicetak ke terminal, tanpa imshow")
    p.add_argument("--debug", action="store_true", help="gambar seluruh 468 landmark")
    return p.parse_args()


def cetak_status(st: Status, fps: float) -> None:
    """Baris status untuk mode headless (menimpa baris yang sama)."""
    tanda = "!!" if st.level == KANTUK else "  "
    alasan = ", ".join(st.alasan) or ("-" if st.ada_wajah else "wajah hilang")
    sys.stdout.write(
        f"\r{tanda} {st.level:<6} | EAR {st.ear_norm * 100:3.0f}% | "
        f"MAR {st.mar_norm * 100:3.0f}% | PERCLOS {st.perclos * 100:3.0f}% | "
        f"kedip {st.kedip_total:3d} | menguap {st.menguap_total:2d} | "
        f"{fps:4.1f} fps | {alasan:<40}"
    )
    sys.stdout.flush()


def main() -> int:
    arg = argumen()
    cfg = Config.muat(arg.config)
    if arg.sumber:
        cfg.kamera.sumber = arg.sumber
    if arg.kalibrasi:
        cfg.kalibrasi_detik = arg.kalibrasi
    tampilkan = cfg.tampilkan_jendela and not arg.tanpa_jendela

    print("=" * 62)
    print(" DETEKSI RASA KANTUK - MediaPipe Face Mesh + EAR/PERCLOS/MAR")
    print("=" * 62)

    detektor = DetektorWajah()
    cap = buka_kamera(cfg.kamera)
    print(f"Kamera   : sumber {cfg.kamera.sumber} -> {info_kamera(cap)}")
    print(f"Kalibrasi: {cfg.kalibrasi_detik:.0f} detik (tatap kamera, mata terbuka wajar)")
    print(f"Mode     : {'jendela OpenCV' if tampilkan else 'headless (terminal)'}")
    print("Tombol   : q keluar | c kalibrasi ulang | d debug landmark\n")

    kalibrator = Kalibrator(cfg.kalibrasi_detik)
    penilai: PenilaiKantuk | None = None
    debug = arg.debug
    fps = 0.0
    t_lalu = time.monotonic()
    cetak_terakhir = 0.0
    gagal_baca = 0
    kode = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                gagal_baca += 1
                if gagal_baca > 30:
                    print("\nKamera berhenti mengirim frame. Program dihentikan.")
                    kode = 1
                    break
                time.sleep(0.03)
                continue
            gagal_baca = 0

            if cfg.kamera.flip_horizontal:
                frame = cv2.flip(frame, 1)

            t = time.monotonic()
            hasil = detektor.proses(frame)

            dt = t - t_lalu
            t_lalu = t
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt

            if penilai is None:
                kalibrator.tambah(hasil, t)
                if kalibrator.selesai(t):
                    baseline = kalibrator.hasil()
                    penilai = PenilaiKantuk(cfg.ambang, baseline)
                    print(f"Baseline : EAR {baseline.ear:.3f} | MAR {baseline.mar:.3f} "
                          f"({baseline.sampel} frame)\n")
                elif tampilkan:
                    gambar_kalibrasi(frame, hasil, kalibrator.sisa_detik(t))
            else:
                st = penilai.perbarui(hasil, t)
                if tampilkan:
                    gambar_overlay(frame, hasil, st, fps, debug)
                elif t - cetak_terakhir > 0.2:
                    cetak_status(st, fps)
                    cetak_terakhir = t

            if tampilkan:
                cv2.imshow("Deteksi Rasa Kantuk", frame)
                tombol = cv2.waitKey(1) & 0xFF
                if tombol in (ord("q"), 27):
                    break
                if tombol == ord("c"):
                    kalibrator = Kalibrator(cfg.kalibrasi_detik)
                    penilai = None
                    print("Kalibrasi ulang...")
                if tombol == ord("d"):
                    debug = not debug
    except KeyboardInterrupt:
        print("\nDihentikan pengguna.")
    finally:
        cap.release()
        detektor.tutup()
        if tampilkan:
            cv2.destroyAllWindows()
        if penilai is not None:
            print(f"\nRingkasan : {penilai.kedip_total} kedipan, "
                  f"{penilai.menguap_total} kali menguap.")
    return kode


if __name__ == "__main__":
    raise SystemExit(main())
