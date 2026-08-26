"""Deteksi wajah & pengukuran mata/mulut dengan MediaPipe Face Mesh."""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

# --- Indeks landmark Face Mesh (468 titik) -----------------------------------
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
    titik: np.ndarray | None = field(default=None, repr=False)  # (468, 2) piksel


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
    """Pembungkus tipis di atas MediaPipe Face Mesh (satu wajah terdekat)."""

    def __init__(self, kepercayaan_deteksi: float = 0.5,
                 kepercayaan_lacak: float = 0.5) -> None:
        import mediapipe as mp

        self._mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=False,   # 468 titik cukup; hemat CPU di Raspberry Pi
            min_detection_confidence=kepercayaan_deteksi,
            min_tracking_confidence=kepercayaan_lacak,
        )

    def proses(self, frame_bgr: np.ndarray) -> HasilDeteksi:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        hasil = self._mesh.process(rgb)
        if not hasil.multi_face_landmarks:
            return HasilDeteksi(ada_wajah=False)

        tinggi, lebar = frame_bgr.shape[:2]
        lm = hasil.multi_face_landmarks[0].landmark
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
        self._mesh.close()
