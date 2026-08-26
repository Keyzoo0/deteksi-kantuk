"""Konfigurasi terpusat. Semua ambang bisa diubah lewat config.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class KameraConfig:
    sumber: str = "0"            # index kamera ("0", "1") atau path file video
    lebar: int = 640
    tinggi: int = 480
    fps: int = 30                # fps yang diminta ke driver kamera
    fourcc: str = "MJPG"         # "MJPG" | "YUYV" | "" (biarkan driver)
    flip_horizontal: bool = True  # tampilan cermin, lebih natural untuk pengguna


@dataclass
class AmbangConfig:
    """Ambang penilaian kantuk.

    Rasio mata & mulut dibandingkan terhadap baseline hasil kalibrasi,
    bukan angka mutlak, supaya tahan terhadap perbedaan bentuk mata,
    jarak ke kamera, dan resolusi webcam.
    """

    rasio_mata_tertutup: float = 0.62    # EAR < 62% baseline dianggap terpejam
    durasi_terpejam_detik: float = 1.2   # terpejam menerus selama ini -> KANTUK
    perclos_window_detik: float = 60.0   # panjang jendela PERCLOS
    perclos_kantuk: float = 0.28         # >28% waktu mata tertutup -> KANTUK
    perclos_min_rentang: float = 30.0    # PERCLOS baru dipercaya setelah sekian detik
    durasi_kedip_maks: float = 0.5       # terpejam lebih lama dari ini bukan kedipan
    # Mulut memakai ambang MUTLAK, bukan rasio terhadap baseline: saat
    # kalibrasi bibir terkatup rapat sehingga baseline MAR nyaris nol
    # (terukur 0.008 pada video uji), dan rasio terhadap angka sekecil itu
    # meledak -- tersenyum saja bisa terbaca 1400% baseline. MAR sendiri
    # sudah dinormalisasi terhadap lebar mulut, jadi cukup seragam antar
    # orang. Pada video uji: mulut biasa 0.01-0.02, menguap 0.72-0.97.
    mar_menguap: float = 0.50            # MAR di atas ini = mulut menganga
    mar_margin_baseline: float = 0.30    # jaga jarak dari baseline tiap orang
    durasi_menguap_detik: float = 0.9    # menganga selama ini baru dihitung menguap
    menguap_per_menit_kantuk: int = 1    # satu kali menguap sudah dianggap kantuk


@dataclass
class Config:
    kamera: KameraConfig = field(default_factory=KameraConfig)
    ambang: AmbangConfig = field(default_factory=AmbangConfig)
    kalibrasi_detik: float = 4.0
    tampilkan_jendela: bool = True

    @classmethod
    def muat(cls, path: str | Path | None) -> "Config":
        cfg = cls()
        if not path or not Path(path).exists():
            return cfg
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cfg.kalibrasi_detik = data.get("kalibrasi_detik", cfg.kalibrasi_detik)
        cfg.tampilkan_jendela = data.get("tampilkan_jendela", cfg.tampilkan_jendela)
        for nama, obj in (("kamera", cfg.kamera), ("ambang", cfg.ambang)):
            for k, v in (data.get(nama) or {}).items():
                if hasattr(obj, k):
                    setattr(obj, k, v)
                else:
                    print(f"[config] kunci tidak dikenal diabaikan: {nama}.{k}")
        return cfg

    def simpan(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
