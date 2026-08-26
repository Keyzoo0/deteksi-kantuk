"""Deteksi wajah & pengukuran mata/mulut dengan MediaPipe Face Landmarker.

Memakai **MediaPipe Tasks API** (`FaceLandmarker`), bukan `mp.solutions.face_mesh`
yang lama: API lama sudah dihapus pada MediaPipe 1.0, sedangkan Tasks API jalan
di MediaPipe 0.10.x maupun 1.x -- jadi kode yang sama dipakai di laptop dan di
Raspberry Pi tanpa peduli versi paketnya.
"""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# Redam log bawaan MediaPipe/TensorFlow Lite. Harus diatur sebelum paketnya
# diimpor (impor mediapipe sengaja ditunda sampai DetektorWajah dibuat).
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import cv2
import numpy as np

from .senyap import redam_stderr

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")
MODEL_DEFAULT = Path(__file__).resolve().parent.parent / "model" / "face_landmarker.task"

# --- Indeks landmark (sama dengan penomoran Face Mesh 468 titik) -------------
# Enam titik EAR per mata, urutan: [sudut luar, atas1, atas2, sudut dalam,
# bawah2, bawah1] -- sesuai rumus Eye Aspect Ratio (Soukupova & Cech, 2016).
EAR_KIRI = (33, 160, 158, 133, 153, 144)
EAR_KANAN = (362, 385, 387, 263, 373, 380)

# Mulut: sudut kiri, sudut kanan, tengah bibir atas (dalam), tengah bibir bawah.
MAR_TITIK = (78, 308, 13, 14)

# Kontur untuk digambar di layar.
KONTUR_MATA_KIRI = (33, 246, 161, 160, 159, 158, 157, 173,
                    133, 155, 154, 153, 145, 144, 163, 7)
KONTUR_MATA_KANAN = (362, 398, 384, 385, 386, 387, 388, 466,
                     263, 249, 390, 373, 374, 380, 381, 382)
KONTUR_MULUT = (78, 95, 88, 178, 87, 14, 317, 402, 318, 324,
                308, 415, 310, 311, 312, 13, 82, 81, 80, 191)


@dataclass
class HasilDeteksi:
    """Pengukuran satu frame."""

    ada_wajah: bool = False
    ear: float = 0.0            # rata-rata Eye Aspect Ratio kiri & kanan
    ear_kiri: float = 0.0
    ear_kanan: float = 0.0
    mar: float = 0.0            # Mouth Aspect Ratio
    kotak_wajah: tuple[int, int, int, int] | None = None   # x, y, w, h
    titik: np.ndarray | None = field(default=None, repr=False)  # (N, 2) piksel


def pastikan_model(path: Path = MODEL_DEFAULT) -> Path:
    """Unduh berkas model bila belum ada (sekali saja, ~3,8 MB)."""
    if path.exists() and path.stat().st_size > 100_000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Mengunduh model face_landmarker ke {path} ...")
    urllib.request.urlretrieve(MODEL_URL, path)
    print(f"Model siap ({path.stat().st_size / 1e6:.1f} MB).")
    return path


def _ear(titik: np.ndarray, idx: tuple[int, ...]) -> float:
    """EAR = (jarak vertikal kelopak) / (2 x jarak horizontal sudut mata)."""
    p = titik[list(idx)]
    lebar = float(np.linalg.norm(p[0] - p[3]))
    if lebar < 1e-6:
        return 0.0
    tinggi = float(np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4]))
    return tinggi / (2.0 * lebar)


def _mar(titik: np.ndarray) -> float:
    """MAR = (bukaan bibir vertikal) / (lebar mulut)."""
    kiri, kanan, atas, bawah = titik[list(MAR_TITIK)]
    lebar = float(np.linalg.norm(kiri - kanan))
    if lebar < 1e-6:
        return 0.0
    return float(np.linalg.norm(atas - bawah) / lebar)


class DetektorWajah:
    """Pembungkus tipis di atas MediaPipe FaceLandmarker (satu wajah terdekat)."""

    def __init__(self, model: Path | str = MODEL_DEFAULT,
                 kepercayaan: float = 0.5) -> None:
        # Impor dan pembuatan graf MediaPipe memuntahkan sederet baris
        # W0000/INFO dari absl & TensorFlow Lite yang tidak bisa dimatikan
        # lewat logging Python.
        with redam_stderr():
            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python import vision

        self._mp = mp
        model = pastikan_model(Path(model))
        opsi = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,   # pelacakan antar frame
            num_faces=1,
            min_face_detection_confidence=kepercayaan,
            min_face_presence_confidence=kepercayaan,
            min_tracking_confidence=kepercayaan,
            output_face_blendshapes=False,           # tidak dipakai, hemat CPU
            output_facial_transformation_matrixes=False,
        )
        with redam_stderr():
            self._landmarker = vision.FaceLandmarker.create_from_options(opsi)
        self._stempel_ms = 0

    def proses(self, frame_bgr: np.ndarray, waktu_ms: int | None = None) -> HasilDeteksi:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        gambar = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)

        # Mode VIDEO menuntut stempel waktu yang selalu naik.
        if waktu_ms is None or waktu_ms <= self._stempel_ms:
            waktu_ms = self._stempel_ms + 1
        self._stempel_ms = waktu_ms

        hasil = self._landmarker.detect_for_video(gambar, waktu_ms)
        if not hasil.face_landmarks:
            return HasilDeteksi(ada_wajah=False)

        tinggi, lebar = frame_bgr.shape[:2]
        lm = hasil.face_landmarks[0]
        titik = np.array([[p.x * lebar, p.y * tinggi] for p in lm], dtype=np.float32)

        kiri, kanan = _ear(titik, EAR_KIRI), _ear(titik, EAR_KANAN)
        x0, y0 = titik[:, 0].min(), titik[:, 1].min()
        x1, y1 = titik[:, 0].max(), titik[:, 1].max()

        return HasilDeteksi(
            ada_wajah=True,
            ear=(kiri + kanan) / 2.0,
            ear_kiri=kiri,
            ear_kanan=kanan,
            mar=_mar(titik),
            kotak_wajah=(int(x0), int(y0), int(x1 - x0), int(y1 - y0)),
            titik=titik,
        )

    def tutup(self) -> None:
        self._landmarker.close()
