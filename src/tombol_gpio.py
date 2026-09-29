"""Tombol fisik dan LED status di GPIO Raspberry Pi.

Alat ini dipakai tanpa monitor maupun keyboard, jadi satu tombol memikul dua
peran yang dibedakan dari lama tekanan:

    ketuk (<1 detik)   -- matikan alarm yang sedang berbunyi (bukti masih sadar)
    tahan 3 detik+     -- (saat siaga) nyalakan sistem
    tahan 8 detik+     -- (saat menyala) matikan sistem untuk istirahat

Ambang tahan bergantung keadaan sistem dan diatur pemanggil lewat
`TombolFisik.atur_tahan()`. Mematikan sengaja jauh lebih lama: tombolnya di
stang, jadi tersenggol beberapa detik saat berkendara masih mungkin.

Tombol ini sengaja TIDAK bisa mematikan Raspberry Pi itu sendiri -- kalau
perlu, matikan lewat SSH (`sudo poweroff`).

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
# Isyarat dikeluarkan SELAGI tombol ditahan, hanya sebagai penanda bagi
# pengguna (suara/LED) bahwa ambang tahan sudah tercapai.
ISYARAT_TAHAN = "isyarat-tahan"

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

    _turun: float | None = None
    _sudah: str | None = None      # peristiwa tahan yang sudah dilaporkan
    # Lama tekanan terakhir yang sudah dilepas, menunggu diambil untuk log.
    # Dicatat untuk SETIAP tekanan -- termasuk yang tidak menghasilkan aksi --
    # supaya grafik log tombol sama persis dengan yang benar-benar terjadi.
    _selesai: float | None = None

    @property
    def sedang_ditekan(self) -> bool:
        return self._turun is not None

    def lama_ditahan(self, t: float) -> float:
        return 0.0 if self._turun is None else max(0.0, t - self._turun)

    def ambil_tekanan(self) -> float | None:
        """Lama tekanan yang baru dilepas (sekali ambil), atau None."""
        lama, self._selesai = self._selesai, None
        return lama

    def perbarui(self, ditekan: bool, t: float) -> str | None:
        """Satu peristiwa per panggilan, atau None.

        Aksi (KETUK/TAHAN) baru dikeluarkan saat tombol DILEPAS, sedangkan
        selagi ditahan hanya keluar isyarat -- supaya pengguna masih bisa
        membatalkan sebelum aksinya benar-benar terjadi.
        """
        if ditekan:
            if self._turun is None:
                self._turun = t
                self._sudah = None
                return None
            lama = t - self._turun
            if lama >= self.tahan and self._sudah is None:
                self._sudah = ISYARAT_TAHAN
                return ISYARAT_TAHAN
            return None

        if self._turun is None:
            return None
        lama = t - self._turun
        self._turun = None
        self._sudah = None
        self._selesai = lama
        if lama >= self.tahan:
            return TAHAN
        if lama <= self.ketuk_maks:
            return KETUK
        return None                       # di antara ketuk dan ambang tahan: diabaikan


class TombolFisik:
    """Pembaca tombol GPIO + LED status; tidak apa-apa bila GPIO tidak ada."""

    def __init__(self, cfg: TombolConfig) -> None:
        self.cfg = cfg
        self.penafsir = PenafsirTombol(cfg.ketuk_maks_detik, cfg.tahan_detik)
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

    def atur_tahan(self, detik: float) -> None:
        """Ganti ambang tahan (3 dtk saat siaga, 8 dtk saat menyala)."""
        self.penafsir.tahan = detik

    def ambil_tekanan(self) -> float | None:
        return self.penafsir.ambil_tekanan()

    def lama_ditahan(self, t: float) -> float:
        return self.penafsir.lama_ditahan(t)

    @property
    def sedang_ditekan(self) -> bool:
        return self.penafsir.sedang_ditekan

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
