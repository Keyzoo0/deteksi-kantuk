"""Tangga alarm tiga tingkat.

    Tingkat 1  peringatan suara berkala selama pengendara terdeteksi mengantuk.
    Tingkat 2  alarm menerus (sirene + suara) yang HANYA berhenti bila tombol
               ditekan -- menekan tombol adalah bukti pengendara masih sadar.
    Tingkat 3  kirim posisi ke kerabat, alarm tetap berbunyi.

Setelah pengendara mengakui (menekan tombol) atau kendaraan terdeteksi berhenti,
tangga kembali ke nol: kejadian berikutnya mulai lagi dari tingkat 1. Ada jeda
singkat sesudahnya supaya alarm tidak langsung menjerit lagi begitu tombol
dilepas.

Kelas ini sengaja tidak menyentuh suara, GPIO, maupun jaringan: ia hanya
mengembalikan daftar peristiwa, dan pemanggil yang memutuskan bunyinya apa.
Dengan begitu seluruh aturan waktunya bisa diuji tanpa perangkat keras.
"""

from __future__ import annotations

from collections import deque

from .config import AlarmConfig

# Tingkat
TENANG, L1, L2, L3 = 0, 1, 2, 3

# Peristiwa yang dikembalikan `perbarui`
BUNYI_L1 = "bunyi-l1"          # ucapkan peringatan "Anda sedang mengantuk"
MULAI_L2 = "mulai-l2"          # nyalakan alarm menerus
BUNYI_L2 = "bunyi-l2"          # ulangi sirene + "tekan tombol"
KIRIM_L3 = "kirim-l3"          # kirim notifikasi + foto ke kerabat
AKUI = "akui"                  # tombol ditekan, alarm berhenti
MENEPI = "menepi"              # kendaraan berhenti, alarm berhenti
SELESAI = "selesai"            # kantuk hilang sendiri sebelum sempat ke L2


class TanggaAlarm:
    def __init__(self, cfg: AlarmConfig) -> None:
        self.cfg = cfg
        self.tingkat = TENANG
        self.kejadian_l3 = 0           # untuk isi pesan "kejadian ke-berapa"
        self._masuk = 0.0              # kapan tingkat sekarang dimulai
        self._bunyi_terakhir = -1e9
        self._kirim_terakhir = -1e9
        self._jeda_sampai = -1e9
        self._riwayat_l1: deque[float] = deque()

    # --- masukan dari pengendara / kendaraan ---------------------------------
    def ketuk(self, t: float) -> list[str]:
        """Tombol ditekan: satu-satunya cara mematikan alarm tingkat 2 ke atas."""
        if self.tingkat == TENANG:
            return []
        return self._reset(t, AKUI)

    def kendaraan_berhenti(self, t: float) -> list[str]:
        """Menepi dianggap setara dengan mengakui: tujuan alarm sudah tercapai."""
        if self.tingkat == TENANG:
            return []
        return self._reset(t, MENEPI)

    def _reset(self, t: float, sebab: str) -> list[str]:
        self.tingkat = TENANG
        self._jeda_sampai = t + self.cfg.jeda_setelah_akui_detik
        self._riwayat_l1.clear()       # tangga benar-benar mulai dari nol lagi
        self._bunyi_terakhir = -1e9
        return [sebab]

    # --- dipanggil tiap frame ------------------------------------------------
    def perbarui(self, mengantuk: bool, t: float, suara_hidup: bool = True) -> list[str]:
        c = self.cfg
        if t < self._jeda_sampai:
            return []

        if not mengantuk:
            # Tingkat 1 boleh reda sendiri; tingkat 2 ke atas tidak. Kantuk yang
            # hilang bukan bukti pengendara sadar -- mata terbuka sesaat itu
            # justru khas orang yang sedang tertidur sebentar-sebentar.
            if self.tingkat == L1:
                self.tingkat = TENANG
                self._bunyi_terakhir = -1e9
                return [SELESAI]
            if self.tingkat == TENANG:
                return []

        if self.tingkat == TENANG:
            self.tingkat = L1
            self._masuk = t
            self._bunyi_terakhir = t
            self._riwayat_l1.append(t)
            self._pangkas(t)
            return [BUNYI_L1]

        if self.tingkat == L1:
            peristiwa = []
            if t - self._bunyi_terakhir >= c.l1_ulang_detik:
                self._bunyi_terakhir = t
                peristiwa.append(BUNYI_L1)
            self._pangkas(t)
            # Naik ke L2 karena kantuk tak kunjung hilang, ATAU karena sudah
            # berulang kali diperingatkan dalam waktu dekat -- kelelahan yang
            # menumpuk lebih berbahaya daripada satu kejadian panjang.
            if (t - self._masuk >= c.l2_setelah_detik
                    or len(self._riwayat_l1) >= c.l2_setelah_l1_berulang):
                self.tingkat = L2
                self._masuk = t
                self._bunyi_terakhir = t
                peristiwa.append(MULAI_L2)
            return peristiwa

        if self.tingkat == L2:
            # Kalau perangkat suara tidak tersambung, menunggu tombol itu
            # percuma: pengendara tidak mendengar apa pun. Langsung minta
            # bantuan alih-alih membuang 10 detik.
            if not suara_hidup or t - self._masuk >= c.l3_setelah_detik:
                self.tingkat = L3
                self._masuk = t
                self.kejadian_l3 += 1
                self._kirim_terakhir = t
                return [KIRIM_L3]
            if t - self._bunyi_terakhir >= c.l2_ulang_detik:
                self._bunyi_terakhir = t
                return [BUNYI_L2]
            return []

        # L3: alarm jalan terus; notifikasi diulang jarang saja agar kerabat
        # tidak dibanjiri pesan.
        peristiwa = []
        if t - self._bunyi_terakhir >= c.l2_ulang_detik:
            self._bunyi_terakhir = t
            peristiwa.append(BUNYI_L2)
        if t - self._kirim_terakhir >= c.l3_ulang_kirim_detik:
            self._kirim_terakhir = t
            self.kejadian_l3 += 1
            peristiwa.append(KIRIM_L3)
        return peristiwa

    def _pangkas(self, t: float) -> None:
        while self._riwayat_l1 and t - self._riwayat_l1[0] > self.cfg.jendela_l1_detik:
            self._riwayat_l1.popleft()
