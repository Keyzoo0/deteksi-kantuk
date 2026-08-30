"""Pembacaan modul GPS NEO-6M lewat UART.

Wiring (Raspberry Pi 5):

    GPS TX  --> pin 10 (GPIO15, RXD)
    GPS RX  <-- pin 8  (GPIO14, TXD)
    GPS VCC --> pin 1 (3V3) atau pin 2 (5V) sesuai modul
    GPS GND --> pin 6

Perangkatnya **/dev/ttyAMA0**, bukan /dev/serial0: di Raspberry Pi 5
`serial0` menunjuk ke UART debug di header 3-pin, bukan ke pin 8/10. UART-nya
diaktifkan dengan `dtoverlay=uart0` di /boot/firmware/config.txt.

Pembacaan dijalankan di thread tersendiri karena aliran NMEA datang ±1 Hz dan
menunggu di loop deteksi akan memangkas FPS. Loop utama cukup membaca
`pembaca.posisi` yang selalu berisi kabar terakhir -- tidak pernah memblokir.

Port dibuka dan dikonfigurasi memakai `termios` dari pustaka standar, jadi
tidak perlu menambah dependensi pyserial hanya untuk membaca teks baris demi
baris.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, replace

from .config import GpsConfig

KNOT_KE_KMH = 1.852


@dataclass(frozen=True)
class Posisi:
    """Kabar terakhir dari modul GPS."""

    valid: bool = False              # True hanya bila modul benar-benar fix
    lat: float = 0.0
    lon: float = 0.0
    kecepatan_kmh: float = 0.0
    satelit: int = 0
    hdop: float = 99.99
    waktu_utc: str = ""
    saat: float = 0.0                # time.monotonic() saat kabar ini diterima

    @property
    def tautan(self) -> str:
        return f"https://maps.google.com/?q={self.lat:.6f},{self.lon:.6f}"

    def ringkas(self) -> str:
        if not self.valid:
            return f"belum fix ({self.satelit} satelit)"
        return (f"{self.lat:.6f}, {self.lon:.6f} | {self.kecepatan_kmh:.1f} km/jam "
                f"| {self.satelit} satelit | HDOP {self.hdop:.1f}")


def _derajat(nilai: str, arah: str) -> float:
    """Ubah format NMEA ddmm.mmmm + arah menjadi derajat desimal."""
    if not nilai or "." not in nilai:
        return 0.0
    titik = nilai.index(".")
    derajat = float(nilai[:titik - 2] or 0)
    menit = float(nilai[titik - 2:])
    hasil = derajat + menit / 60.0
    return -hasil if arah in ("S", "W") else hasil


class PenguraiNmea:
    """Kumpulkan kalimat NMEA menjadi satu gambaran posisi.

    Dipisah dari pembacaan port supaya bisa diuji dengan kalimat rekaman.
    """

    def __init__(self) -> None:
        self.posisi = Posisi()

    def telan(self, baris: str, saat: float | None = None) -> Posisi:
        baris = baris.strip()
        if not baris.startswith("$") or "," not in baris:
            return self.posisi
        k = baris.split("*")[0].split(",")
        jenis, p = k[0][-3:], self.posisi
        saat = time.monotonic() if saat is None else saat
        try:
            if jenis == "RMC" and len(k) >= 8:
                valid = k[2] == "A"
                p = replace(
                    p, valid=valid, waktu_utc=k[1], saat=saat,
                    lat=_derajat(k[3], k[4]) if valid else p.lat,
                    lon=_derajat(k[5], k[6]) if valid else p.lon,
                    kecepatan_kmh=(float(k[7]) * KNOT_KE_KMH) if valid and k[7] else 0.0)
            elif jenis == "GGA" and len(k) >= 9:
                p = replace(p, saat=saat,
                            satelit=int(k[7]) if k[7].isdigit() else p.satelit,
                            hdop=float(k[8]) if k[8] else p.hdop)
            elif jenis == "GSV" and len(k) >= 4:
                # Dipakai saat belum fix: menunjukkan modul sudah "mendengar"
                # satelit atau belum -- pembeda antara antena bermasalah dan
                # sekadar butuh waktu lebih lama.
                if not p.valid and k[3].isdigit():
                    p = replace(p, satelit=int(k[3]), saat=saat)
        except (ValueError, IndexError):
            return self.posisi            # kalimat rusak diabaikan diam-diam
        self.posisi = p
        return p


class PantauBerhenti:
    """Apakah kendaraan sudah benar-benar berhenti, bukan sekadar melambat?"""

    def __init__(self, cfg: GpsConfig) -> None:
        self.cfg = cfg
        self._diam_sejak: float | None = None

    def perbarui(self, posisi: Posisi, t: float) -> bool:
        # Tanpa fix, kecepatan tidak diketahui. Diam-diam menganggap "berhenti"
        # akan mematikan alarm justru saat sinyal hilang -- persis keadaan yang
        # tidak boleh dipercaya.
        if not posisi.valid:
            self._diam_sejak = None
            return False
        if posisi.kecepatan_kmh > self.cfg.ambang_berhenti_kmh:
            self._diam_sejak = None
            return False
        if self._diam_sejak is None:
            self._diam_sejak = t
        return t - self._diam_sejak >= self.cfg.berhenti_detik


class PembacaGps:
    """Thread pembaca /dev/ttyAMA0; aman dipakai walau modulnya tidak ada."""

    def __init__(self, cfg: GpsConfig) -> None:
        self.cfg = cfg
        self.pengurai = PenguraiNmea()
        self.pantau = PantauBerhenti(cfg)
        self._fd = -1
        self._jalan = False
        self._kunci = threading.Lock()
        self._posisi = Posisi()
        self.keterangan = "dimatikan"

        if not cfg.aktif:
            return
        try:
            self._fd = self._buka(cfg.port, cfg.baud)
        except OSError as e:
            self.keterangan = f"tidak tersedia ({cfg.port}: {e.strerror or e})"
            return
        self.keterangan = f"{cfg.port} @ {cfg.baud} baud"
        self._jalan = True
        threading.Thread(target=self._baca, daemon=True).start()

    @staticmethod
    def _buka(port: str, baud: int) -> int:
        import termios

        fd = os.open(port, os.O_RDONLY | os.O_NOCTTY)
        laju = getattr(termios, f"B{baud}")
        iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(fd)
        iflag = termios.IGNPAR
        oflag = lflag = 0
        cflag = termios.CS8 | termios.CREAD | termios.CLOCAL
        cc = list(cc)
        cc[termios.VMIN], cc[termios.VTIME] = 0, 10      # tunggu maksimal 1 detik
        termios.tcsetattr(fd, termios.TCSANOW,
                          [iflag, oflag, cflag, lflag, laju, laju, cc])
        return fd

    def _baca(self) -> None:
        sisa = b""
        while self._jalan:
            try:
                data = os.read(self._fd, 512)
            except OSError:
                time.sleep(1.0)
                continue
            if not data:
                continue
            sisa += data
            *baris, sisa = sisa.split(b"\n")
            for b in baris:
                posisi = self.pengurai.telan(b.decode("ascii", "replace"))
                with self._kunci:
                    self._posisi = posisi

    @property
    def posisi(self) -> Posisi:
        with self._kunci:
            return self._posisi

    def berhenti(self, t: float) -> bool:
        return self.pantau.perbarui(self.posisi, t)

    def tutup(self) -> None:
        self._jalan = False
        if self._fd >= 0:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = -1
