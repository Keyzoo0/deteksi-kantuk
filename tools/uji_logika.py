"""Uji logika penilaian kantuk dan asisten suara tanpa kamera.

Frame disimulasikan (bukan dari webcam) sehingga bagian pengambilan keputusan
bisa diperiksa sendiri: kedipan tidak boleh memicu alarm, mata terpejam lama
harus memicu, menguap harus terhitung, PERCLOS harus naik, dan peringatan
lisan harus berbunyi pada ambang yang benar (termasuk sistem mati sendiri
saat wajah lama tidak terlihat).

Jalankan: .venv/bin/python tools/uji_logika.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import AmbangConfig, Config              # noqa: E402
from src.deteksi import HasilDeteksi                     # noqa: E402
from src.main import Sesi, _tahap_kalibrasi, _tahap_monitor   # noqa: E402
from src.metrik import (AMAN, KANTUK, Baseline, Kalibrator,   # noqa: E402
                        PenilaiKantuk, Status)
from src.suara import (ARAHKAN, MATI, MENGANTUK, MULAI_KALIBRASI,  # noqa: E402
                       AsistenSuara)

EAR_BUKA, EAR_TUTUP = 0.30, 0.12
MAR_TUTUP, MAR_NGANGA = 0.05, 0.60
FPS = 20.0
LANGKAH = 1.0 / FPS

BASELINE = Baseline(ear=EAR_BUKA, mar=MAR_TUTUP, sampel=100)


def _frame(ear: float, mar: float = MAR_TUTUP) -> HasilDeteksi:
    return HasilDeteksi(ada_wajah=True, ear=ear, mar=mar)


def jalankan(penilai: PenilaiKantuk, t0: float, detik: float,
             ear: float, mar: float = MAR_TUTUP):
    """Umpankan frame selama `detik`, kembalikan (waktu_akhir, status_terakhir)."""
    t = t0
    st = None
    for _ in range(int(detik * FPS)):
        st = penilai.perbarui(_frame(ear, mar), t)
        t += LANGKAH
    return t, st


class AsistenPalsu(AsistenSuara):
    """Asisten yang mencatat pesan alih-alih membunyikannya."""

    def __init__(self, cfg) -> None:
        super().__init__(cfg, Path(__file__).resolve().parent.parent)
        self.diucapkan: list[str] = []
        self._bicara = False

    @property
    def sedang_bicara(self) -> bool:      # dikendalikan uji, bukan proses nyata
        return self._bicara

    @property
    def terjadwal(self) -> list[str]:
        """Pesan yang sudah berbunyi maupun yang masih mengantre."""
        return [*self.diucapkan, *self._antrean]

    def _mulai(self, kunci: str) -> bool:
        import time
        self.diucapkan.append(kunci)
        self._terakhir[kunci] = time.monotonic()
        return True


def uji(nama: str, syarat: bool, catatan: str = "") -> bool:
    tanda = "LULUS" if syarat else "GAGAL"
    print(f"  [{tanda}] {nama}" + (f" -- {catatan}" if catatan else ""))
    return syarat


def main() -> int:
    a = AmbangConfig()
    hasil: list[bool] = []

    print("1. Kedipan normal tidak boleh dianggap kantuk")
    p = PenilaiKantuk(a, BASELINE)
    t = 0.0
    for _ in range(10):                       # 10 kedipan, masing-masing 0.15 detik
        t, _ = jalankan(p, t, 1.85, EAR_BUKA)
        t, st = jalankan(p, t, 0.15, EAR_TUTUP)
    t, st = jalankan(p, t, 1.0, EAR_BUKA)
    hasil.append(uji("level tetap AMAN", st.level == AMAN, f"level={st.level}"))
    hasil.append(uji("kedipan terhitung", 8 <= st.kedip_total <= 10,
                     f"{st.kedip_total} kedipan"))
    hasil.append(uji("PERCLOS rendah", st.perclos < a.perclos_kantuk,
                     f"{st.perclos * 100:.0f}%"))

    print("\n2. Mata terpejam lama harus memicu KANTUK")
    p = PenilaiKantuk(a, BASELINE)
    t, _ = jalankan(p, 0.0, 3.0, EAR_BUKA)
    t, st = jalankan(p, t, 1.0, EAR_TUTUP)    # belum melewati 1.2 detik
    hasil.append(uji("0.95 detik terpejam: masih AMAN", st.level == AMAN,
                     f"durasi={st.durasi_tertutup:.2f}s"))
    t, st = jalankan(p, t, 1.0, EAR_TUTUP)    # total ~2 detik
    hasil.append(uji("2 detik terpejam: KANTUK", st.level == KANTUK,
                     ", ".join(st.alasan)))

    print("\n3. PERCLOS tinggi (mata setengah menutup terus) harus memicu KANTUK")
    p = PenilaiKantuk(a, BASELINE)
    t = 0.0
    for _ in range(20):                       # 1 detik buka, 1 detik tutup -> ~50%
        t, _ = jalankan(p, t, 1.0, EAR_BUKA)
        t, st = jalankan(p, t, 1.0, EAR_TUTUP)
    hasil.append(uji("PERCLOS >= ambang", st.perclos >= a.perclos_kantuk,
                     f"{st.perclos * 100:.0f}%"))
    hasil.append(uji("level KANTUK", st.level == KANTUK, ", ".join(st.alasan)))

    print("\n4. Menguap: sesaat tidak dihitung, dan KANTUK hanya selama menguap")
    p = PenilaiKantuk(a, BASELINE)
    t, _ = jalankan(p, 0.0, 2.0, EAR_BUKA)
    t, st = jalankan(p, t, 0.4, EAR_BUKA, MAR_NGANGA)     # bicara, 0.4 detik
    t, st = jalankan(p, t, 1.0, EAR_BUKA)
    hasil.append(uji("nganga 0.4 detik tidak dihitung", st.menguap_total == 0,
                     f"{st.menguap_total}x"))
    hasil.append(uji("level tetap AMAN", st.level == AMAN, f"level={st.level}"))

    t, st = jalankan(p, t, 2.0, EAR_BUKA, MAR_NGANGA)     # menguap penuh
    hasil.append(uji("menguap terhitung", st.menguap_total == 1, f"{st.menguap_total}x"))
    hasil.append(uji("KANTUK selagi menguap", st.level == KANTUK, ", ".join(st.alasan)))

    t, st = jalankan(p, t, 3.0, EAR_BUKA)                 # mulut menutup lagi
    hasil.append(uji("kembali AMAN setelah mulut menutup", st.level == AMAN,
                     f"level={st.level}, menguap tercatat {st.menguap_total}x"))

    print("\n5. Wajah hilang tidak boleh memicu alarm palsu")
    p = PenilaiKantuk(a, BASELINE)
    t, _ = jalankan(p, 0.0, 2.0, EAR_BUKA)
    st = None
    for _ in range(int(3.0 * FPS)):
        st = p.perbarui(HasilDeteksi(ada_wajah=False), t)
        t += LANGKAH
    hasil.append(uji("level tetap AMAN", st.level == AMAN, ", ".join(st.alasan) or "-"))

    print("\n6. Suara kantuk: ambangnya lebih longgar daripada tulisan di layar")
    cfg = Config()
    asisten = AsistenPalsu(cfg.suara)
    sesi = Sesi(Kalibrator(cfg.kalibrasi_detik), penilai=object())  # type: ignore[arg-type]
    st = Status(ada_wajah=True, durasi_tertutup=2.0)
    _tahap_monitor(cfg, sesi, asisten, st, 10.0, False)
    hasil.append(uji("terpejam 2 detik: belum bersuara", asisten.diucapkan == [],
                     f"{asisten.diucapkan}"))
    st = Status(ada_wajah=True, durasi_tertutup=3.1)
    _tahap_monitor(cfg, sesi, asisten, st, 11.0, False)
    hasil.append(uji("terpejam 3.1 detik: bersuara", asisten.diucapkan == [MENGANTUK],
                     f"{asisten.diucapkan}"))
    _tahap_monitor(cfg, sesi, asisten, st, 11.1, False)
    hasil.append(uji("tidak diulang sebelum jeda habis",
                     asisten.diucapkan == [MENGANTUK], f"{asisten.diucapkan}"))

    asisten = AsistenPalsu(cfg.suara)
    sesi = Sesi(Kalibrator(cfg.kalibrasi_detik), penilai=object())  # type: ignore[arg-type]
    _tahap_monitor(cfg, sesi, asisten, Status(ada_wajah=True, durasi_menguap=1.5),
                   10.0, False)
    hasil.append(uji("menguap 1.5 detik: belum bersuara", asisten.diucapkan == [],
                     f"{asisten.diucapkan}"))
    _tahap_monitor(cfg, sesi, asisten, Status(ada_wajah=True, durasi_menguap=2.1),
                   10.5, False)
    hasil.append(uji("menguap 2.1 detik: bersuara", asisten.diucapkan == [MENGANTUK],
                     f"{asisten.diucapkan}"))

    print("\n7. Wajah hilang: dituntun suara, lalu sistem mati sendiri")
    asisten = AsistenPalsu(cfg.suara)
    sesi = Sesi(Kalibrator(cfg.kalibrasi_detik), penilai=object())  # type: ignore[arg-type]
    kosong = Status(ada_wajah=False)
    mati, catatan = _tahap_monitor(cfg, sesi, asisten, kosong, 0.0, False)
    hasil.append(uji("baru hilang: belum bersuara",
                     asisten.diucapkan == [] and not mati, f"{asisten.diucapkan}"))
    mati, catatan = _tahap_monitor(cfg, sesi, asisten, kosong,
                                   cfg.suara.wajah_hilang_detik + 0.1, False)
    hasil.append(uji("hilang 3 detik: minta arahkan kamera",
                     asisten.diucapkan == [ARAHKAN], f"{asisten.diucapkan}"))
    hasil.append(uji("layar menampilkan hitung mundur", catatan.startswith("MATI DALAM"),
                     catatan))
    mati, _ = _tahap_monitor(cfg, sesi, asisten, kosong,
                             cfg.mati_tanpa_wajah_detik - 0.1, False)
    hasil.append(uji("sebelum 1 menit: sistem masih hidup", not mati))
    mati, _ = _tahap_monitor(cfg, sesi, asisten, kosong,
                             cfg.mati_tanpa_wajah_detik + 0.1, False)
    hasil.append(uji("lewat 1 menit: sistem mati", mati and MATI in asisten.diucapkan,
                     f"{asisten.diucapkan}"))

    print("\n8. Kalibrasi baru merekam setelah instruksinya selesai diucapkan")
    asisten = AsistenPalsu(cfg.suara)
    sesi = Sesi(Kalibrator(1.0))
    wajah = HasilDeteksi(ada_wajah=True, ear=EAR_BUKA, mar=MAR_TUTUP)
    asisten._bicara = True                     # instruksi sedang berbunyi
    _tahap_kalibrasi(cfg, sesi, asisten, wajah, 0.0)
    hasil.append(uji("instruksi kalibrasi dijadwalkan sekali",
                     asisten.terjadwal == [MULAI_KALIBRASI], f"{asisten.terjadwal}"))
    hasil.append(uji("baseline belum direkam selagi bicara",
                     not sesi.kalibrator.dimulai))
    asisten._bicara = False                    # instruksi selesai
    t = 1.0
    while sesi.penilai is None and t < 12.0:
        _tahap_kalibrasi(cfg, sesi, asisten, wajah, t)
        t += LANGKAH
    hasil.append(uji("baseline terekam setelah instruksi selesai",
                     sesi.penilai is not None, f"selesai pada t={t:.1f}s"))

    lulus = sum(hasil)
    print(f"\n{'=' * 46}\n{lulus}/{len(hasil)} pemeriksaan lulus")
    return 0 if lulus == len(hasil) else 1


if __name__ == "__main__":
    sys.exit(main())
