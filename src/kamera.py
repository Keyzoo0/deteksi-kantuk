"""Pembukaan dan pembacaan webcam dengan penanganan galat yang jelas."""

from __future__ import annotations

import cv2

from .config import KameraConfig


def buka_kamera(cfg: KameraConfig) -> cv2.VideoCapture:
    """Buka webcam (atau file video) sesuai konfigurasi.

    Di Linux backend V4L2 dipilih eksplisit: lebih cepat dibuka dan lebih
    stabil untuk webcam USB, termasuk di Raspberry Pi.
    """
    sumber: int | str = int(cfg.sumber) if str(cfg.sumber).isdigit() else str(cfg.sumber)

    if isinstance(sumber, int):
        cap = cv2.VideoCapture(sumber, cv2.CAP_V4L2)
        if not cap.isOpened():                     # fallback bila V4L2 tak tersedia
            cap = cv2.VideoCapture(sumber)
    else:
        cap = cv2.VideoCapture(sumber)

    if not cap.isOpened():
        raise RuntimeError(
            f"Kamera '{cfg.sumber}' tidak bisa dibuka. "
            "Cek daftar perangkat dengan: ls /dev/video* , "
            "atau ganti index lewat --sumber 1"
        )

    if isinstance(sumber, int):
        # MJPG supaya webcam USB sanggup 640x480 pada fps tinggi tanpa membebani USB.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.lebar)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.tinggi)
        cap.set(cv2.CAP_PROP_FPS, cfg.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)        # kurangi lag frame lama
    return cap


def info_kamera(cap: cv2.VideoCapture) -> str:
    return (f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
            f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ "
            f"{cap.get(cv2.CAP_PROP_FPS):.0f} fps")
