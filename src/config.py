"""Konfigurasi terpusat. Semua ambang bisa diubah lewat config.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class KameraConfig:
    # "auto" = pakai kamera pertama yang cocok dengan `merek`. Nomor index
    # berbeda-beda antar mesin (di laptop uji C270 ada di 2, di Raspberry Pi di
    # 0), jadi menuliskannya di config justru bikin berkas ini tidak bisa
    # dipakai bersama. Isi angka hanya bila ingin mendahulukan satu index.
    sumber: str = "auto"         # "auto" | index kamera ("0") | path file video
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
    # Kamera di motor dipasang miring di dekat spion, jadi frame perlu diputar
    # sebelum dinilai. Putaran dilakukan SEBELUM deteksi, bukan hanya di
    # tampilan: MediaPipe mencari wajah tegak, dan wajah miring 90 derajat
    # praktis tidak terdeteksi sama sekali.
    putar: int = 0               # 0 | 90 | 180 | 270 derajat searah jarum jam
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
    jeda_tanpa_internet_detik: float = 10.0  # pengingat "tidak ada internet"
    pemutar: str = ""                    # kosong = deteksi otomatis


@dataclass
class WebConfig:
    """Web server pemantauan lokal (lihat src/web.py)."""

    aktif: bool = True
    host: str = "0.0.0.0"                # semua antarmuka: WiFi maupun kabel
    port: int = 8080
    fps_video: int = 5                   # video langsung sengaja dibatasi
    mutu_jpeg: int = 60
    jeda_sampel_detik: float = 1.0       # satu titik grafik per detik
    jendela_detik: float = 7200.0        # panjang grafik: 2 jam
    folder_web: str = "web/dist"         # hasil `npm run build` di folder web/
    berkas_info: str = "info.json"       # isi tab Info, bisa diubah dari web
    logo_bawaan: str = "aset/logo-undip.png"
    logo_unggah: str = "data/logo.png"   # logo yang diunggah pengguna


@dataclass
class NotifikasiConfig:
    """Notifikasi ke kerabat lewat Telegram (lihat src/notifikasi.py).

    Token bot dan daftar chat sengaja TIDAK di sini: `config.json` ikut masuk
    repo, sedangkan token bot adalah kunci penuh ke bot itu. Keduanya dibaca
    dari `rahasia.json` yang diabaikan git.
    """

    aktif: bool = True
    berkas_rahasia: str = "rahasia.json"
    berkas_antrean: str = "antrean_notifikasi.jsonl"
    kirim_foto: bool = True              # foto hanya disertakan pada alarm tingkat 3
    batas_detik: float = 15.0            # batas tunggu tiap panggilan HTTP
    jeda_coba_ulang_detik: float = 60.0  # jarak percobaan ulang pesan tertunda
    jeda_cek_daring_detik: float = 15.0  # jarak pemeriksaan koneksi internet


@dataclass
class GpsConfig:
    """Modul GPS NEO-6M lewat UART (lihat src/gps.py)."""

    aktif: bool = True
    # Di Raspberry Pi 5, /dev/serial0 menunjuk ke UART debug di header 3-pin,
    # BUKAN ke pin 8/10. Jadi porta yang benar untuk modul GPS adalah ttyAMA0.
    port: str = "/dev/ttyAMA0"
    baud: int = 9600
    ambang_berhenti_kmh: float = 3.0     # di bawah ini dianggap tidak melaju
    berhenti_detik: float = 30.0         # selama ini -> kendaraan dianggap menepi


@dataclass
class AlarmConfig:
    """Tangga alarm tiga tingkat (lihat src/alarm.py).

    Ambang di sini terpisah dari `SuaraConfig`: `SuaraConfig` mengatur KAPAN
    seseorang dianggap mengantuk, `AlarmConfig` mengatur seberapa keras
    tanggapannya bila kantuk itu tidak juga hilang.
    """

    l1_ulang_detik: float = 5.0          # jeda ulang peringatan tingkat 1
    l2_setelah_detik: float = 10.0       # kantuk bertahan sekian -> tingkat 2
    l2_setelah_l1_berulang: int = 3      # sekian peringatan dalam jendela -> tingkat 2
    jendela_l1_detik: float = 600.0      # jendela hitungan peringatan berulang
    l2_ulang_detik: float = 4.0          # jeda ulang sirene tingkat 2
    l3_setelah_detik: float = 10.0       # tingkat 2 tanpa tombol sekian -> tingkat 3
    l3_ulang_kirim_detik: float = 300.0  # jarak minimum antar notifikasi
    jeda_setelah_akui_detik: float = 60.0  # tenang sejenak setelah tombol ditekan


@dataclass
class TombolConfig:
    """Tombol fisik + LED status di GPIO (lihat src/tombol_gpio.py).

    Satu tombol memikul dua peran, dibedakan dari lama tekanan, karena alat
    ini dipakai tanpa monitor maupun keyboard.
    """

    aktif: bool = True
    pin: int = 21                        # GPIO21 = pin fisik 40 (GND di pin 39)
    pin_led: int = 27                    # GPIO27 = pin fisik 13; 0 = tanpa LED
    ketuk_maks_detik: float = 1.0        # <= ini dianggap ketukan pendek
    tahan_detik: float = 3.0             # tahan sekian -> kalibrasi ulang
    debounce_detik: float = 0.05


@dataclass
class Config:
    kamera: KameraConfig = field(default_factory=KameraConfig)
    ambang: AmbangConfig = field(default_factory=AmbangConfig)
    suara: SuaraConfig = field(default_factory=SuaraConfig)
    tombol: TombolConfig = field(default_factory=TombolConfig)
    alarm: AlarmConfig = field(default_factory=AlarmConfig)
    gps: GpsConfig = field(default_factory=GpsConfig)
    notifikasi: NotifikasiConfig = field(default_factory=NotifikasiConfig)
    web: WebConfig = field(default_factory=WebConfig)
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
                          ("suara", cfg.suara), ("tombol", cfg.tombol),
                          ("alarm", cfg.alarm), ("gps", cfg.gps),
                          ("notifikasi", cfg.notifikasi), ("web", cfg.web)):
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
