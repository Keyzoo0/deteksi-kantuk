"""Uji logika penilaian kantuk tanpa kamera.

Frame disimulasikan (bukan dari webcam) sehingga bagian pengambilan keputusan
bisa diperiksa sendiri: kedipan tidak boleh memicu alarm, mata terpejam lama
harus memicu, menguap harus terhitung, dan PERCLOS harus naik.

Jalankan: .venv/bin/python tools/uji_logika.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import AmbangConfig                      # noqa: E402
from src.deteksi import HasilDeteksi                     # noqa: E402
from src.metrik import AMAN, KANTUK, Baseline, PenilaiKantuk  # noqa: E402

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

    print("\n4. Menguap: sesaat tidak dihitung, lama dihitung")
    p = PenilaiKantuk(a, BASELINE)
    t, _ = jalankan(p, 0.0, 2.0, EAR_BUKA)
    t, st = jalankan(p, t, 0.4, EAR_BUKA, MAR_NGANGA)     # bicara, 0.4 detik
    t, st = jalankan(p, t, 1.0, EAR_BUKA)
    hasil.append(uji("nganga 0.4 detik tidak dihitung", st.menguap_total == 0,
                     f"{st.menguap_total}x"))
    for _ in range(3):                                     # 3 kali menguap 1.5 detik
        t, _ = jalankan(p, t, 1.5, EAR_BUKA, MAR_NGANGA)
        t, st = jalankan(p, t, 1.5, EAR_BUKA)
    hasil.append(uji("3 kali menguap terhitung", st.menguap_total == 3,
                     f"{st.menguap_total}x"))
    hasil.append(uji("level KANTUK karena menguap", st.level == KANTUK,
                     ", ".join(st.alasan)))

    print("\n5. Wajah hilang tidak boleh memicu alarm palsu")
    p = PenilaiKantuk(a, BASELINE)
    t, _ = jalankan(p, 0.0, 2.0, EAR_BUKA)
    st = None
    for _ in range(int(3.0 * FPS)):
        st = p.perbarui(HasilDeteksi(ada_wajah=False), t)
        t += LANGKAH
    hasil.append(uji("level tetap AMAN", st.level == AMAN, ", ".join(st.alasan) or "-"))

    lulus = sum(hasil)
    print(f"\n{'=' * 46}\n{lulus}/{len(hasil)} pemeriksaan lulus")
    return 0 if lulus == len(hasil) else 1


if __name__ == "__main__":
    sys.exit(main())
