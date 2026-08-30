"""Asisten suara: sapaan, panduan, dan peringatan lisan lewat speaker.

Enam pesan yang dipakai program (lihat `PESAN`): sapaan awal, panduan
mengarahkan kamera, pengumuman kalibrasi, tanda sistem siap, peringatan
kantuk, dan pemberitahuan sistem dimatikan.

Suara diambil dari berkas WAV yang sudah jadi di folder `suara/` (hasil TTS
neural Bahasa Indonesia, lihat `tools/buat_suara.py`), bukan disintesis saat
program berjalan. Alasannya: pengucapannya jauh lebih enak didengar daripada
espeak, tidak butuh internet maupun CPU saat berkendara, dan peringatan
langsung berbunyi tanpa jeda sintesis. Bila berkasnya tidak ada, program jatuh
ke TTS sistem (espeak-ng/spd-say) -- robotik, tetapi lebih baik daripada bisu.

Pemutaran dijalankan sebagai proses terpisah dan tidak ditunggu, supaya loop
deteksi tetap berjalan penuh selagi suara berbunyi.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from .config import SuaraConfig

SALAM = "salam"
ARAHKAN = "arahkan-kamera"
MULAI_KALIBRASI = "mulai-kalibrasi"
SIAP = "siap"
MENGANTUK = "mengantuk"
MATI = "mati"

# Kalimat setiap pesan. Dipakai dua tempat: `tools/buat_suara.py` merekamnya
# jadi WAV, dan TTS cadangan mengucapkannya langsung bila WAV-nya hilang.
PESAN: dict[str, str] = {
    SALAM: ("Halo, saya adalah asisten pribadi monitoring rasa kantuk saat "
            "berkendara. Tekan tombol spasi untuk memulai sistem."),
    ARAHKAN: "Arahkan kamera ke wajah Anda.",
    MULAI_KALIBRASI: ("Memulai kalibrasi. Arahkan dan tahan wajah Anda "
                      "menghadap ke kamera."),
    SIAP: "Kalibrasi selesai. Sistem monitoring dimulai.",
    MENGANTUK: "Anda sedang mengantuk, silakan menepi.",
    MATI: "Wajah tidak terdeteksi lebih dari satu menit. Sistem dimatikan.",
}

# Pemutar berkas WAV, diurutkan dari yang paling ringan. pw-play/paplay ada di
# desktop modern (PipeWire/PulseAudio); aplay selalu ada di Raspberry Pi OS.
PEMUTAR: tuple[tuple[str, list[str]], ...] = (
    ("pw-play", []),
    ("paplay", []),
    ("aplay", ["-q"]),
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ("mpv", ["--no-video", "--really-quiet"]),
    ("play", ["-q"]),                       # sox
)

# Cadangan bila berkas suara hilang: TTS sistem.
TTS: tuple[tuple[str, list[str]], ...] = (
    ("espeak-ng", ["-v", "id", "-s", "145"]),
    ("espeak", ["-v", "id", "-s", "145"]),
    ("spd-say", ["-w", "-l", "id"]),
)


class AsistenSuara:
    """Pemutar pesan lisan, lengkap dengan jeda ulang dan antrean pendek."""

    def __init__(self, cfg: SuaraConfig, akar: Path) -> None:
        self.cfg = cfg
        self.aktif = cfg.aktif
        self._proses: subprocess.Popen | None = None
        self._terakhir: dict[str, float] = {}
        self._antrean: list[str] = []

        folder = Path(cfg.folder)
        if not folder.is_absolute():
            folder = akar / folder
        self._berkas = {k: folder / f"{k}-{cfg.voice}.wav" for k in PESAN}
        self._ada = {k: v for k, v in self._berkas.items() if v.exists()}
        self._pemutar = self._cari([(cfg.pemutar, [])] if cfg.pemutar else list(PEMUTAR))
        self._tts = self._cari(list(TTS))
        self.keterangan = self._keterangan(folder)

    # --- penyiapan -----------------------------------------------------------
    @staticmethod
    def _cari(kandidat: list[tuple[str, list[str]]]) -> list[str] | None:
        for nama, opsi in kandidat:
            jalur = shutil.which(nama)
            if jalur:
                return [jalur, *opsi]
        return None

    def _keterangan(self, folder: Path) -> str:
        if not self.aktif:
            return "dimatikan (--tanpa-suara)"
        if self._ada and self._pemutar:
            kurang = [k for k in PESAN if k not in self._ada]
            pesan = (f"{len(self._ada)}/{len(PESAN)} berkas suara '{self.cfg.voice}' "
                     f"lewat {Path(self._pemutar[0]).name}")
            if kurang and self._tts:
                pesan += f" (belum ada: {', '.join(kurang)} -> TTS sistem)"
            elif kurang:
                pesan += f" (BELUM ADA: {', '.join(kurang)} -> bisu)"
            return pesan
        if self._tts:
            return (f"TTS sistem ({Path(self._tts[0]).name}); berkas suara tidak "
                    f"ditemukan di {folder} -- jalankan tools/buat_suara.py")
        self.aktif = False
        return ("TIDAK ADA pemutar suara; pasang salah satu: "
                "pw-play / paplay / aplay / espeak-ng")

    # --- pemutaran -----------------------------------------------------------
    @property
    def sedang_bicara(self) -> bool:
        return self._proses is not None and self._proses.poll() is None

    def _perintah(self, kunci: str) -> list[str] | None:
        berkas = self._ada.get(kunci)
        if berkas is not None and self._pemutar:
            return [*self._pemutar, str(berkas)]
        if self._tts:
            return [*self._tts, PESAN.get(kunci, "")]
        return None

    def _mulai(self, kunci: str) -> bool:
        perintah = self._perintah(kunci)
        if perintah is None:
            return False
        try:
            self._proses = subprocess.Popen(
                perintah, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.aktif = False                  # pemutar hilang di tengah jalan
            return False
        self._terakhir[kunci] = time.monotonic()
        return True

    def ucap(self, kunci: str, antre: bool = False, paksa: bool = False) -> bool:
        """Bunyikan satu pesan.

        `antre`  : pesan penting -- kalau speaker sedang dipakai, tunggu giliran
                   alih-alih hangus (dipakai untuk sapaan dan panduan tahapan).
        `paksa`  : abaikan jeda ulang (dipakai saat pesan memang harus berbunyi
                   sekali di titik itu, mis. saat sistem baru dinyalakan).
        """
        if not self.aktif:
            return False
        sekarang = time.monotonic()
        # Jeda ulang memakai jam dinding, bukan waktu video, supaya peringatan
        # tidak beruntun saat menganalisis berkas video lebih cepat dari waktu
        # nyata.
        if not paksa and sekarang - self._terakhir.get(kunci, -1e9) < self.cfg.jeda_ulang_detik:
            return False
        if self.sedang_bicara:
            if antre and kunci not in self._antrean:
                self._antrean.append(kunci)
                self._terakhir[kunci] = sekarang     # cukup sekali per jeda
                return True
            return False
        return self._mulai(kunci)

    def layani(self) -> None:
        """Panggil tiap frame: jalankan pesan berikutnya begitu speaker bebas."""
        if self.aktif and self._antrean and not self.sedang_bicara:
            self._mulai(self._antrean.pop(0))

    def diam(self) -> None:
        """Hentikan suara yang sedang berbunyi dan kosongkan antrean."""
        self._antrean.clear()
        if self.sedang_bicara:
            self._proses.terminate()            # type: ignore[union-attr]
        self._proses = None

    def tutup(self) -> None:
        self.diam()
