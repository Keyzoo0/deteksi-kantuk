"""Kalibrasi baseline dan penilaian tingkat kantuk dari deretan frame."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from statistics import median

from .config import AmbangConfig
from .deteksi import HasilDeteksi

AMAN, KANTUK = "AMAN", "KANTUK"


@dataclass
class Baseline:
    """Nilai acuan pengguna saat sadar penuh, hasil kalibrasi."""

    ear: float
    mar: float
    sampel: int


class Kalibrator:
    """Kumpulkan EAR/MAR saat pengguna melihat kamera dengan mata terbuka.

    Timer baru mulai berjalan ketika wajah pertama kali terlihat, jadi
    pengguna tidak "kehabisan waktu" saat masih mengatur posisi kamera.
    """

    def __init__(self, durasi_detik: float) -> None:
        self.durasi = durasi_detik
        self._ear: list[float] = []
        self._mar: list[float] = []
        self._mulai: float | None = None

    @property
    def dimulai(self) -> bool:
        """True setelah wajah pertama kali terlihat (timer sudah berjalan)."""
        return self._mulai is not None

    def sisa_detik(self, t: float) -> float:
        if self._mulai is None:
            return self.durasi
        return max(0.0, self.durasi - (t - self._mulai))

    def tambah(self, hasil: HasilDeteksi, t: float) -> None:
        if not hasil.ada_wajah:
            return
        if self._mulai is None:
            self._mulai = t
        self._ear.append(hasil.ear)
        self._mar.append(hasil.mar)

    def selesai(self, t: float) -> bool:
        return self._mulai is not None and self.sisa_detik(t) <= 0 and len(self._ear) >= 10

    def hasil(self) -> Baseline:
        # Median, bukan rata-rata: kebal terhadap frame nyeleneh saat pengguna
        # kebetulan berkedip di tengah kalibrasi.
        return Baseline(ear=median(self._ear), mar=median(self._mar), sampel=len(self._ear))


@dataclass
class Status:
    """Ringkasan kondisi pengguna pada satu frame."""

    level: str = AMAN
    alasan: list[str] = field(default_factory=list)
    ada_wajah: bool = True
    mata_tertutup: bool = False
    durasi_tertutup: float = 0.0
    ear_norm: float = 1.0        # 1.0 = sama seperti saat kalibrasi
    mar: float = 0.0             # nilai MAR mentah
    ambang_mar: float = 0.0      # ambang menguap yang sedang dipakai
    perclos: float = 0.0
    perclos_matang: bool = False  # True bila jendela pengamatan sudah cukup panjang
    kedip_total: int = 0
    kedip_per_menit: int = 0
    menguap_total: int = 0
    menguap_per_menit: int = 0
    sedang_menguap: bool = False
    durasi_menguap: float = 0.0  # lama mulut menganga tanpa putus


class PenilaiKantuk:
    """Mesin status: mengubah pengukuran per-frame menjadi level AMAN/KANTUK."""

    def __init__(self, ambang: AmbangConfig, baseline: Baseline) -> None:
        self.a = ambang
        self.b = baseline
        # Ambang menguap: nilai mutlak, tapi tidak pernah lebih dekat dari
        # margin tertentu ke bibir terkatup orang ini.
        self.ambang_mar = max(ambang.mar_menguap, baseline.mar + ambang.mar_margin_baseline)

        self._jendela: deque[tuple[float, bool]] = deque()  # (waktu, mata_tertutup)
        self._kedip: deque[float] = deque()
        self._menguap: deque[float] = deque()

        self._tertutup_sejak: float | None = None
        self._menguap_sejak: float | None = None
        self._menguap_tercatat = False
        self._hilang_sejak: float | None = None
        self.kedip_total = 0
        self.menguap_total = 0

    def perbarui(self, hasil: HasilDeteksi, t: float) -> Status:
        a, b = self.a, self.b
        st = Status(ada_wajah=hasil.ada_wajah)

        if not hasil.ada_wajah:
            # Wajah hilang: hentikan hitungan terpejam agar tidak salah alarm,
            # tapi jendela PERCLOS tetap dipangkas supaya angkanya tidak beku.
            self._tertutup_sejak = None
            self._menguap_sejak = None
            if self._hilang_sejak is None:
                self._hilang_sejak = t
            self._pangkas(self._jendela, t, a.perclos_window_detik)
            st.perclos = self._perclos()
            st.perclos_matang = self._rentang() >= a.perclos_min_rentang
            st.kedip_total, st.menguap_total = self.kedip_total, self.menguap_total
            if t - self._hilang_sejak > 3.0:
                st.alasan.append("wajah tidak terdeteksi")
            return st
        self._hilang_sejak = None

        st.ear_norm = hasil.ear / b.ear if b.ear > 1e-6 else 1.0
        st.mar = hasil.mar
        st.ambang_mar = self.ambang_mar

        self._perbarui_mata(st, t)
        self._perbarui_mulut(st, t)

        st.kedip_total, st.menguap_total = self.kedip_total, self.menguap_total
        self._tentukan_level(st)
        return st

    # --- bagian mata ---------------------------------------------------------
    def _perbarui_mata(self, st: Status, t: float) -> None:
        a = self.a
        tertutup = st.ear_norm < a.rasio_mata_tertutup
        st.mata_tertutup = tertutup

        self._jendela.append((t, tertutup))
        self._pangkas(self._jendela, t, a.perclos_window_detik)
        st.perclos = self._perclos()
        st.perclos_matang = self._rentang() >= a.perclos_min_rentang

        if tertutup:
            if self._tertutup_sejak is None:
                self._tertutup_sejak = t
            st.durasi_tertutup = t - self._tertutup_sejak
            return

        if self._tertutup_sejak is not None:
            lama = t - self._tertutup_sejak
            if 0.04 <= lama <= a.durasi_kedip_maks:   # durasi khas satu kedipan
                self.kedip_total += 1
                self._kedip.append(t)
        self._tertutup_sejak = None
        self._pangkas(self._kedip, t, 60.0)
        st.kedip_per_menit = len(self._kedip)

    # --- bagian mulut --------------------------------------------------------
    def _perbarui_mulut(self, st: Status, t: float) -> None:
        a = self.a
        if st.mar > self.ambang_mar:
            if self._menguap_sejak is None:
                self._menguap_sejak = t
                self._menguap_tercatat = False
            # Menganga sesaat (bicara) tidak dihitung; harus bertahan dulu.
            st.durasi_menguap = t - self._menguap_sejak
            st.sedang_menguap = st.durasi_menguap >= a.durasi_menguap_detik
            if st.sedang_menguap and not self._menguap_tercatat:
                self.menguap_total += 1
                self._menguap.append(t)
                self._menguap_tercatat = True
        else:
            self._menguap_sejak = None
            self._menguap_tercatat = False

        self._pangkas(self._menguap, t, 60.0)
        st.menguap_per_menit = len(self._menguap)
        self._pangkas(self._kedip, t, 60.0)
        st.kedip_per_menit = len(self._kedip)

    # --- util ----------------------------------------------------------------
    @staticmethod
    def _pangkas(d: deque, t: float, window: float) -> None:
        while d:
            waktu = d[0][0] if isinstance(d[0], tuple) else d[0]
            if t - waktu <= window:
                break
            d.popleft()

    def _rentang(self) -> float:
        """Panjang waktu yang benar-benar tercakup jendela pengamatan."""
        if len(self._jendela) < 2:
            return 0.0
        return self._jendela[-1][0] - self._jendela[0][0]

    def _perclos(self) -> float:
        """Persentase waktu mata tertutup dalam jendela pengamatan."""
        if len(self._jendela) < 10:
            return 0.0
        return sum(1 for _, tertutup in self._jendela if tertutup) / len(self._jendela)

    def _tentukan_level(self, st: Status) -> None:
        a = self.a
        alasan: list[str] = []

        if st.durasi_tertutup >= a.durasi_terpejam_detik:
            alasan.append(f"mata terpejam {st.durasi_tertutup:.1f} detik")
        # PERCLOS dari jendela yang baru terisi sebentar mudah menipu: satu
        # kedipan panjang di detik-detik awal bisa terbaca 50%.
        if st.perclos_matang and st.perclos >= a.perclos_kantuk:
            alasan.append(f"PERCLOS {st.perclos * 100:.0f}%")
        # Menguap menandai kantuk selama menguapnya berlangsung; begitu mulut
        # menutup, penilaian kembali bergantung pada mata.
        if a.kantuk_saat_menguap and st.sedang_menguap:
            alasan.append("sedang menguap")
        if a.menguap_per_menit_kantuk > 0 and st.menguap_per_menit >= a.menguap_per_menit_kantuk:
            alasan.append(f"menguap {st.menguap_per_menit}x/menit")

        st.level = KANTUK if alasan else AMAN
        st.alasan = alasan
