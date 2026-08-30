"""Pembukaan dan pembacaan webcam dengan penanganan galat yang jelas."""

from __future__ import annotations

import glob
import time
from dataclasses import dataclass
from pathlib import Path

import cv2

from .config import KameraConfig
from .senyap import redam_stderr

# Nama merek -> idVendor USB. Nama perangkat V4L2 tidak selalu memuat mereknya
# (webcam Logitech C270 mendaftar sebagai "C270 HD WEBCAM" saja, dan berkas
# `manufacturer`-nya malah berisi nama pengendali USB), jadi penyaringan
# utamanya memakai idVendor yang selalu benar.
VENDOR_MEREK = {
    "logitech": ("046d",),
    "logi": ("046d",),
}


@dataclass(frozen=True)
class Perangkat:
    """Satu node /dev/videoN beserta identitas USB-nya."""

    index: int
    nama: str = ""          # nama V4L2, mis. "C270 HD WEBCAM"
    vendor: str = ""        # idVendor USB, mis. "046d"
    produk: str = ""        # string produk USB
    pabrikan: str = ""      # string pabrikan USB (sering tidak diisi perangkat)

    def cocok(self, merek: str) -> bool:
        """Benarkah perangkat ini berasal dari merek yang diminta?

        `merek` boleh berupa nama ("logitech"), idVendor ("046d"), atau potongan
        nama perangkat ("c270"). Merek kosong berarti semua kamera diterima.
        """
        kunci = merek.strip().lower()
        if not kunci:
            return True
        if kunci in VENDOR_MEREK:
            return self.vendor in VENDOR_MEREK[kunci]
        if kunci == self.vendor:
            return True
        return any(kunci in teks.lower()
                   for teks in (self.nama, self.produk, self.pabrikan) if teks)

    def label(self) -> str:
        nama = self.nama or self.produk or "kamera tanpa nama"
        return f"/dev/video{self.index} ({nama}{f', {self.vendor}' if self.vendor else ''})"


def _baca(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _identitas_usb(index: int) -> tuple[str, str, str]:
    """(idVendor, product, manufacturer) dari perangkat USB induk node video."""
    tautan = Path(f"/sys/class/video4linux/video{index}/device")
    try:
        induk = tautan.resolve()
    except OSError:
        return "", "", ""
    # Node video menggantung pada antarmuka USB (mis. 3-2:1.0); berkas
    # idVendor ada satu tingkat di atasnya, tetapi ditelusuri beberapa tingkat
    # supaya tetap ketemu pada susunan sysfs yang berbeda.
    for _ in range(4):
        induk = induk.parent
        vendor = _baca(induk / "idVendor")
        if vendor:
            return vendor, _baca(induk / "product"), _baca(induk / "manufacturer")
    return "", "", ""


def daftar_perangkat() -> list[Perangkat]:
    """Semua node /dev/videoN yang ada di sistem, urut menaik."""
    hasil = []
    for path in sorted(glob.glob("/dev/video*")):
        angka = "".join(c for c in path if c.isdigit())
        if not angka:
            continue
        index = int(angka)
        vendor, produk, pabrikan = _identitas_usb(index)
        hasil.append(Perangkat(index, _baca(Path(f"/sys/class/video4linux/video{index}/name")),
                               vendor, produk, pabrikan))
    return sorted(hasil, key=lambda p: p.index)


def perangkat_merek(merek: str) -> list[Perangkat]:
    """Node video milik merek yang diminta saja."""
    return [p for p in daftar_perangkat() if p.cocok(merek)]


def cari_perangkat(index: int) -> Perangkat:
    for p in daftar_perangkat():
        if p.index == index:
            return p
    return Perangkat(index)


def _coba_buka(index: int, cfg: KameraConfig) -> cv2.VideoCapture | None:
    """Buka satu index dan pastikan benar-benar mengirim frame."""
    # Index yang mati membuat OpenCV mencetak beberapa baris peringatan V4L2;
    # itu wajar saat menjajal, jadi diredam. Kegagalan tetap tertangkap lewat
    # nilai balik None.
    with redam_stderr(tetap_tampilkan_bila_galat=False):
        return _buka_sekali(index, cfg)


def _buka_sekali(index: int, cfg: KameraConfig) -> cv2.VideoCapture | None:
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(index)          # fallback bila V4L2 tak tersedia
        if not cap.isOpened():
            cap.release()
            return None

    # MJPG dipakai secara default. Aliran YUYV 640x480 butuh ~18 MB/s dan
    # banyak webcam USB tidak sanggup: frame datang setengah jadi sehingga
    # gambar tampak "robek" (teruji: 21 dari 30 frame robek pada YUYV,
    # 4 dari 30 pada MJPG). Ganti ke "YUYV" lewat config bila webcam Anda
    # justru bermasalah dengan MJPG.
    if cfg.fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*cfg.fourcc[:4]))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.lebar)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.tinggi)
    cap.set(cv2.CAP_PROP_FPS, cfg.fps)
    # Catatan: CAP_PROP_BUFFERSIZE=1 sengaja TIDAK dipakai. Di beberapa
    # webcam UVC, antrean 1 buffer justru memangkas throughput sampai
    # separuh (teruji: 16.5 -> 8.5 fps), sementara lag antar frame tidak
    # terasa karena loop deteksi jauh lebih cepat daripada kamera.

    # Perangkat /dev/video* tidak selalu berupa kamera: satu webcam sering
    # mendaftarkan dua node, yang satu hanya untuk metadata dan tidak pernah
    # mengirim gambar. Karena itu keberhasilan diukur dari frame, bukan dari
    # isOpened() saja.
    for _ in range(5):
        ok, frame = cap.read()
        if ok and frame is not None:
            return cap
    cap.release()
    return None


def _pesan_tidak_ada(merek: str) -> str:
    lain = daftar_perangkat()
    baris = [f"Kamera {merek} tidak terpasang. Program tidak bisa jalan tanpa kamera itu."]
    if lain:
        baris.append("  Kamera yang terbaca sekarang (bukan " + merek + "):")
        baris += [f"    - {p.label()}" for p in lain]
    else:
        baris.append("  Tidak ada /dev/video* sama sekali.")
    baris += [
        f"  - Tancapkan webcam {merek}-nya, lalu jalankan lagi.",
        "  - Cek perangkat  : ls /dev/video*",
        "  - Cek pemakai    : fuser -v /dev/video*   (tutup aplikasi lain "
        "yang memakai kamera)",
        "  - Lihat daftar   : .venv/bin/python tools/cek_kamera.py",
        f'  - Terima kamera merek lain: setel "merek" di config.json '
        f"(kosongkan untuk menerima semua) atau jalankan dengan --merek ''",
    ]
    return "\n".join(baris)


def pastikan_kamera_ada(cfg: KameraConfig) -> None:
    """Pastikan kamera merek yang diminta tertancap, tanpa membukanya.

    Dipakai saat program baru mulai: pemeriksaan cukup lewat sysfs sehingga
    lampu kamera tidak sempat menyala, sedangkan aliran videonya baru dibuka
    ketika pengguna menekan SPASI.
    """
    merek = (cfg.merek or "").strip()
    if not str(cfg.sumber).isdigit():
        return
    if not perangkat_merek(merek):
        raise RuntimeError(_pesan_tidak_ada(merek or "apa pun"))


def buka_kamera(cfg: KameraConfig) -> cv2.VideoCapture:
    """Buka webcam (atau file video) sesuai konfigurasi.

    Hanya kamera bermerek `cfg.merek` yang dipakai -- secara default Logitech.
    Kamera lain (mis. kamera bawaan laptop) sengaja tidak dipilih walaupun
    tersedia, supaya deteksi selalu memakai perangkat yang sama. Kalau kamera
    itu sedang tidak tertancap, program berhenti dengan pesan yang jelas.

    Index /dev/videoN yang tertulis di config diperlakukan sebagai pilihan
    pertama saja, karena penomorannya bisa bergeser setelah webcam dicabut,
    di-reset, atau setelah reboot -- node lain milik merek yang sama dicoba
    otomatis.
    """
    if not str(cfg.sumber).isdigit():                  # file video / URL
        cap = cv2.VideoCapture(str(cfg.sumber))
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"Sumber video '{cfg.sumber}' tidak bisa dibuka.")
        return cap

    merek = (cfg.merek or "").strip()
    calon = perangkat_merek(merek)
    if not calon:
        raise RuntimeError(_pesan_tidak_ada(merek or "apa pun"))

    diminta = int(cfg.sumber)
    # Index yang diminta didahulukan bila memang milik merek tersebut.
    urutan = ([p for p in calon if p.index == diminta]
              + [p for p in calon if p.index != diminta])
    for p in urutan:
        cap = _coba_buka(p.index, cfg)
        if cap is not None:
            if p.index != diminta:
                print(f"[kamera] index {diminta} tidak dipakai, "
                      f"memakai {p.label()}.")
            cfg.sumber = str(p.index)
            return cap

    daftar = ", ".join(p.label() for p in calon)
    raise RuntimeError(
        f"Kamera {merek or 'apa pun'} terbaca ({daftar}) tetapi tidak mengirim "
        "gambar sama sekali.\n"
        "  - Cek pemakai    : fuser -v /dev/video*   (tutup aplikasi lain "
        "yang memakai kamera)\n"
        "  - Coba format lain lewat config.json (mis. \"fourcc\": \"YUYV\")\n"
        "  - Uji tiap format: .venv/bin/python tools/cek_kamera.py"
    )


def info_kamera(cap: cv2.VideoCapture) -> str:
    return (f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
            f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ "
            f"{cap.get(cv2.CAP_PROP_FPS):.0f} fps")


def sambung_ulang(cap: cv2.VideoCapture | None, cfg: KameraConfig,
                  percobaan: int = 12, jeda: float = 1.0) -> cv2.VideoCapture | None:
    """Buka ulang kamera setelah aliran frame terputus.

    Sebagian webcam sesekali lepas dari bus USB lalu muncul kembali dengan
    nomor /dev/videoN yang berbeda. Karena `buka_kamera` memang menyapu semua
    node milik merek yang dipakai, cukup panggil ulang sampai perangkatnya
    kembali. Kalau yang muncul kembali bukan kamera merek itu, penyambungan
    tetap dianggap gagal.
    """
    if cap is not None:
        cap.release()
    for ke in range(1, percobaan + 1):
        time.sleep(jeda)
        try:
            with redam_stderr(tetap_tampilkan_bila_galat=False):
                baru = buka_kamera(cfg)
            print(f"[kamera] tersambung kembali (percobaan {ke}).")
            return baru
        except RuntimeError:
            continue
    return None
