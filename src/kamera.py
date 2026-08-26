"""Pembukaan dan pembacaan webcam dengan penanganan galat yang jelas."""

from __future__ import annotations

import glob
import time

import cv2

from .config import KameraConfig
from .senyap import redam_stderr


def daftar_index() -> list[int]:
    """Index /dev/videoN yang ada di sistem, urut menaik."""
    index = []
    for path in sorted(glob.glob("/dev/video*")):
        angka = "".join(c for c in path if c.isdigit())
        if angka:
            index.append(int(angka))
    return sorted(index)


def _coba_buka(index: int, cfg: KameraConfig) -> cv2.VideoCapture | None:
    """Buka satu index dan pastikan benar-benar mengirim frame."""
    # Index yang mati membuat OpenCV mencetak beberapa baris peringatan V4L2;
    # itu wajar saat menjajal, jadi diredam. Kegagalan tetap tertangkap lewat
    # nilai balik None.
    with redam_stderr(tetap_tampilkan_bila_galat=False):
        return _buka_sekali(index, cfg)


def _buka_sekali(index: int, cfg: KameraConfig) -> cv2.VideoCapture | None:
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(index)          # fallback bila V4L2 tak tersedia
        if not cap.isOpened():
            cap.release()
            return None

    # MJPG dipakai secara default. Aliran YUYV 640x480 butuh ~18 MB/s dan
    # banyak webcam USB tidak sanggup: frame datang setengah jadi sehingga
    # gambar tampak "robek" (teruji: 21 dari 30 frame robek pada YUYV,
    # 4 dari 30 pada MJPG). Ganti ke "YUYV" lewat config bila webcam Anda
    # justru bermasalah dengan MJPG.
    if cfg.fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*cfg.fourcc[:4]))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.lebar)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.tinggi)
    cap.set(cv2.CAP_PROP_FPS, cfg.fps)
    # Catatan: CAP_PROP_BUFFERSIZE=1 sengaja TIDAK dipakai. Di beberapa
    # webcam UVC, antrean 1 buffer justru memangkas throughput sampai
    # separuh (teruji: 16.5 -> 8.5 fps), sementara lag antar frame tidak
    # terasa karena loop deteksi jauh lebih cepat daripada kamera.

    # Perangkat /dev/video* tidak selalu berupa kamera: satu webcam sering
    # mendaftarkan dua node, yang satu hanya untuk metadata dan tidak pernah
    # mengirim gambar. Karena itu keberhasilan diukur dari frame, bukan dari
    # isOpened() saja.
    for _ in range(5):
        ok, frame = cap.read()
        if ok and frame is not None:
            return cap
    cap.release()
    return None


def buka_kamera(cfg: KameraConfig) -> cv2.VideoCapture:
    """Buka webcam (atau file video) sesuai konfigurasi.

    Bila index yang diminta tidak tersedia -- hal biasa karena penomoran
    /dev/videoN bisa bergeser setelah webcam dicabut, di-reset, atau setelah
    reboot -- index lain yang ada di sistem dicoba otomatis.
    """
    if not str(cfg.sumber).isdigit():                  # file video / URL
        cap = cv2.VideoCapture(str(cfg.sumber))
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"Sumber video '{cfg.sumber}' tidak bisa dibuka.")
        return cap

    diminta = int(cfg.sumber)
    cap = _coba_buka(diminta, cfg)
    if cap is not None:
        return cap

    tersedia = [i for i in daftar_index() if i != diminta]
    for index in tersedia:
        cap = _coba_buka(index, cfg)
        if cap is not None:
            print(f"[kamera] index {diminta} tidak mengirim gambar, "
                  f"memakai index {index}.")
            cfg.sumber = str(index)
            return cap

    raise RuntimeError(
        f"Tidak ada kamera yang bisa dipakai (index {diminta} gagal"
        + (f", sudah dicoba juga {tersedia}" if tersedia else ", tidak ada /dev/video*")
        + ").\n"
        "  - Cek perangkat  : ls /dev/video*\n"
        "  - Cek pemakai    : fuser -v /dev/video*   (tutup aplikasi lain "
        "yang memakai kamera)\n"
        "  - Uji tiap format: .venv/bin/python tools/cek_kamera.py"
    )


def info_kamera(cap: cv2.VideoCapture) -> str:
    return (f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
            f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ "
            f"{cap.get(cv2.CAP_PROP_FPS):.0f} fps")


def sambung_ulang(cap: cv2.VideoCapture | None, cfg: KameraConfig,
                  percobaan: int = 12, jeda: float = 1.0) -> cv2.VideoCapture | None:
    """Buka ulang kamera setelah aliran frame terputus.

    Sebagian webcam (terutama kamera internal laptop dan webcam USB berdaya
    kecil) sesekali lepas dari bus USB lalu muncul kembali dengan nomor
    /dev/videoN yang berbeda. Karena `buka_kamera` memang menyapu semua index
    yang ada, cukup panggil ulang sampai perangkatnya kembali.
    """
    if cap is not None:
        cap.release()
    for ke in range(1, percobaan + 1):
        time.sleep(jeda)
        try:
            with redam_stderr(tetap_tampilkan_bila_galat=False):
                baru = buka_kamera(cfg)
            print(f"[kamera] tersambung kembali (percobaan {ke}).")
            return baru
        except RuntimeError:
            continue
    return None
