"""Konfigurasi terpusat. Semua ambang bisa diubah lewat config.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class KameraConfig:
    sumber: str = "0"            # index kamera ("0", "1") atau path file video
    # Hanya kamera bermerek ini yang dipakai; kamera lain (mis. kamera bawaan
    # laptop) diabaikan walau tersedia, dan program berhenti bila kamera yang
    # dimaksud tidak tertancap. Boleh diisi nama merek ("logitech"), idVendor
    # USB ("046d"), atau potongan nama perangkat ("c270"). Kosongkan untuk
    # menerima kamera apa pun.
    merek: str = "logitech"
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
    kantuk_saat_menguap: bool = True     # KANTUK selama menguap berlangsung saja
    # Aturan tambahan berbasis laju menguap. Bernilai 0 = dimatikan. Kalau
    # diaktifkan (mis. 3), status KANTUK bertahan selama menguap masih masuk
    # hitungan 60 detik terakhir -- alarm ikut menyala walau mulut sudah
    # tertutup dan mata segar.
    menguap_per_menit_kantuk: int = 0


@dataclass
class SuaraConfig:
    """Asisten suara: sapaan, panduan, dan peringatan lisan.

    Ambang di sini sengaja terpisah dari `AmbangConfig`: tulisan KANTUK di
    layar boleh muncul cepat (1,2 detik terpejam), sedangkan suara baru
    berbunyi saat kondisinya benar-benar meyakinkan supaya tidak cerewet.
    """

    aktif: bool = True
    voice: str = "gadis"                 # "gadis" (perempuan) | "ardi" (laki-laki)
    folder: str = "suara"                # tempat berkas <pesan>-<voice>.wav
    terpejam_detik: float = 3.0          # mata terpejam selama ini -> bersuara
    menguap_detik: float = 2.0           # menguap selama ini -> bersuara
    wajah_hilang_detik: float = 3.0      # wajah tak terlihat selama ini -> bersuara
    jeda_ulang_detik: float = 5.0        # pesan yang sama paling cepat diulang
    pemutar: str = ""                    # kosong = deteksi otomatis


@dataclass
class Config:
    kamera: KameraConfig = field(default_factory=KameraConfig)
    ambang: AmbangConfig = field(default_factory=AmbangConfig)
    suara: SuaraConfig = field(default_factory=SuaraConfig)
    kalibrasi_detik: float = 4.0
    # Wajah hilang selama ini saat monitoring -> sistem dimatikan sendiri dan
    # kembali ke layar siaga (pengemudi turun, kamera bergeser, dsb.).
    mati_tanpa_wajah_detik: float = 60.0
    tampilkan_jendela: bool = True

    @classmethod
    def muat(cls, path: str | Path | None) -> "Config":
        cfg = cls()
        if not path or not Path(path).exists():
            return cfg
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cfg.kalibrasi_detik = data.get("kalibrasi_detik", cfg.kalibrasi_detik)
        cfg.tampilkan_jendela = data.get("tampilkan_jendela", cfg.tampilkan_jendela)
        cfg.mati_tanpa_wajah_detik = data.get("mati_tanpa_wajah_detik",
                                              cfg.mati_tanpa_wajah_detik)
        for nama, obj in (("kamera", cfg.kamera), ("ambang", cfg.ambang),
                          ("suara", cfg.suara)):
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
