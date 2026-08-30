"""Tombol fisik dan LED status di GPIO Raspberry Pi.

Alat ini dipakai tanpa monitor maupun keyboard, jadi satu tombol memikul tiga
peran yang dibedakan dari lama tekanan:

    ketuk (<1 detik)   -- matikan alarm yang sedang berbunyi (bukti masih sadar)
    tahan 3 detik      -- nyalakan sistem, atau matikan sistem untuk istirahat
    tahan 8 detik      -- matikan Raspberry Pi dengan aman

Wiring (Raspberry Pi 5):

    tombol momentary:  GPIO21 (pin fisik 40)  <-->  GND (pin fisik 39)
                       (di motor, tombolnya dipasang di stang dekat jempol kiri
                        supaya bisa ditekan tanpa melepas genggaman)
    LED status     :  GPIO27 (pin fisik 13)  --[330 ohm]-->  GND (pin fisik 14)

Tombol memakai pull-up internal sehingga pin diam di HIGH dan turun ke LOW saat
ditekan (active low). Tidak ada resistor luar yang diperlukan. JANGAN
menyambungkan tombol ke 3,3 V atau 5 V: GPIO Raspberry Pi tidak toleran 5 V.

Penafsiran lama tekanan sengaja dipisah ke `PenafsirTombol` yang tidak menyentuh
perangkat keras sama sekali, supaya logikanya bisa diuji di laptop tanpa GPIO.
"""

from __future__ import annotations

import signal
from dataclasses import dataclass

from .config import TombolConfig

KETUK = "ketuk"
TAHAN = "tahan"
TAHAN_LAMA = "tahan-lama"
# Isyarat dikeluarkan SELAGI tombol ditahan, hanya sebagai penanda bagi
# pengguna (suara/LED) bahwa ambang berikutnya sudah tercapai.
ISYARAT_TAHAN = "isyarat-tahan"
ISYARAT_TAHAN_LAMA = "isyarat-tahan-lama"

# Pola LED status.
PADAM, NYALA, KEDIP_LAMBAT, KEDIP_CEPAT = "padam", "nyala", "kedip-lambat", "kedip-cepat"

_sinyal: list[str] = []          # tombol tiruan lewat SIGUSR1/SIGUSR2


def _tangkap(sig, _frame) -> None:
    _sinyal.append(KETUK if sig == signal.SIGUSR1 else TAHAN)


@dataclass
class PenafsirTombol:
    """Ubah deretan pembacaan ditekan/lepas menjadi peristiwa bermakna."""

    ketuk_maks: float = 1.0
    tahan: float = 3.0
    tahan_lama: float = 8.0

    _turun: float | None = None
    _sudah: str | None = None      # peristiwa tahan yang sudah dilaporkan

    def perbarui(self, ditekan: bool, t: float) -> str | None:
        """Satu peristiwa per panggilan, atau None.

        Aksi (KETUK/TAHAN/TAHAN_LAMA) baru dikeluarkan saat tombol DILEPAS,
        sedangkan selagi ditahan hanya keluar isyarat. Kalau aksi dijalankan
        selagi ditahan, menahan 8 detik untuk mematikan Pi akan lebih dulu
        memicu kalibrasi ulang di detik ke-3 -- pengguna tidak punya
        kesempatan membatalkan, padahal keduanya tindakan yang tidak ringan.
        """
        if ditekan:
            if self._turun is None:
                self._turun = t
                self._sudah = None
                return None
            lama = t - self._turun
            if lama >= self.tahan_lama and self._sudah != ISYARAT_TAHAN_LAMA:
                self._sudah = ISYARAT_TAHAN_LAMA
                return ISYARAT_TAHAN_LAMA
            if self.tahan <= lama < self.tahan_lama and self._sudah is None:
                self._sudah = ISYARAT_TAHAN
                return ISYARAT_TAHAN
            return None

        if self._turun is None:
            return None
        lama = t - self._turun
        self._turun = None
        self._sudah = None
        if lama >= self.tahan_lama:
            return TAHAN_LAMA
        if lama >= self.tahan:
            return TAHAN
        if lama <= self.ketuk_maks:
            return KETUK
        return None                       # 1-3 detik: rentang ambigu, diabaikan


class TombolFisik:
    """Pembaca tombol GPIO + LED status; tidak apa-apa bila GPIO tidak ada."""

    def __init__(self, cfg: TombolConfig) -> None:
        self.cfg = cfg
        self.penafsir = PenafsirTombol(cfg.ketuk_maks_detik, cfg.tahan_detik,
                                       cfg.tahan_lama_detik)
        self._btn = None
        self._led = None
        self._pola = None
        self.keterangan = "dimatikan"

        # Tombol tiruan: `kill -USR1 <pid>` = ketuk, `-USR2` = tahan. Dipakai
        # untuk menguji lewat SSH sebelum tombolnya terpasang.
        for sig in (signal.SIGUSR1, signal.SIGUSR2):
            try:
                signal.signal(sig, _tangkap)
            except (ValueError, OSError):     # bukan thread utama
                pass

        if not cfg.aktif:
            return
        try:
            from gpiozero import LED, Button
            self._btn = Button(cfg.pin, pull_up=True, bounce_time=cfg.debounce_detik)
            self.keterangan = f"GPIO{cfg.pin} (pin fisik 40), pull-up internal"
            if cfg.pin_led:
                self._led = LED(cfg.pin_led)
                self.keterangan += f" | LED GPIO{cfg.pin_led}"
        except Exception as e:            # bukan Pi, pustaka tak ada, pin sibuk
            self.keterangan = f"tidak tersedia ({type(e).__name__}: {e})"

    @property
    def ada(self) -> bool:
        return self._btn is not None

    @property
    def ditekan(self) -> bool:
        return bool(self._btn and self._btn.is_pressed)

    def periksa(self, t: float) -> str | None:
        """Panggil tiap frame; kembalikan peristiwa tombol bila ada."""
        if _sinyal:
            return _sinyal.pop(0)
        if self._btn is None:
            return None
        return self.penafsir.perbarui(self._btn.is_pressed, t)

    def pola_led(self, pola: str) -> None:
        if self._led is None or pola == self._pola:
            return
        self._pola = pola
        if pola == NYALA:
            self._led.on()
        elif pola == KEDIP_CEPAT:
            self._led.blink(on_time=0.12, off_time=0.12, background=True)
        elif pola == KEDIP_LAMBAT:
            self._led.blink(on_time=0.6, off_time=1.4, background=True)
        else:
            self._led.off()

    def tutup(self) -> None:
        for alat in (self._led, self._btn):
            if alat is not None:
                try:
                    alat.close()
                except Exception:
                    pass
