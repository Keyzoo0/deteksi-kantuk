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

from src.alarm import (AKUI, BUNYI_L1, BUNYI_L2, KIRIM_L3, MULAI_L2,   # noqa: E402
                       SELESAI, L1, L2, L3, TENANG, TanggaAlarm)
from src.config import (AlarmConfig, AmbangConfig, Config,   # noqa: E402
                        GpsConfig)
from src.gps import PantauBerhenti, PenguraiNmea, Posisi  # noqa: E402
from src.tombol_gpio import ISYARAT_TAHAN, KETUK, TAHAN, PenafsirTombol  # noqa: E402
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

    print("\n9. Tangga alarm: naik bertingkat, hanya tombol yang menghentikan")
    ca = AlarmConfig()
    tangga = TanggaAlarm(ca)

    def jalan(tangga, t0, detik, mengantuk, suara=True, langkah=0.5):
        t, catat = t0, []
        for _ in range(int(detik / langkah)):
            catat += tangga.perbarui(mengantuk, t, suara)
            t += langkah
        return t, catat

    t, catat = jalan(tangga, 0.0, 6.0, True)
    hasil.append(uji("mengantuk 6 dtk: tingkat 1, bunyi berkala",
                     tangga.tingkat == L1 and catat.count(BUNYI_L1) == 2, f"{catat}"))
    t, catat = jalan(tangga, t, 6.0, True)
    hasil.append(uji("lewat 10 dtk: naik ke tingkat 2",
                     tangga.tingkat == L2 and MULAI_L2 in catat, f"tingkat={tangga.tingkat}"))
    t, catat = jalan(tangga, t, 6.0, False)     # kantuk "hilang", tombol belum ditekan
    hasil.append(uji("kantuk hilang tidak mematikan tingkat 2",
                     tangga.tingkat >= L2, f"tingkat={tangga.tingkat}"))
    t, catat = jalan(tangga, t, 8.0, True)
    hasil.append(uji("tingkat 2 tanpa tombol: naik ke tingkat 3",
                     tangga.tingkat == L3 and KIRIM_L3 in catat, f"{catat}"))
    hasil.append(uji("ketukan mematikan alarm dan mengembalikan ke nol",
                     tangga.ketuk(t) == [AKUI] and tangga.tingkat == TENANG))
    t, catat = jalan(tangga, t, 30.0, True)
    hasil.append(uji("jeda 60 dtk setelah diakui: alarm diam", catat == [], f"{catat}"))
    t, catat = jalan(tangga, t + 40.0, 2.0, True)
    hasil.append(uji("setelah jeda habis: mulai lagi dari tingkat 1",
                     tangga.tingkat == L1 and BUNYI_L1 in catat, f"tingkat={tangga.tingkat}"))

    print("\n10. Alarm melompat ke tingkat 3 bila perangkat suara mati")
    tangga = TanggaAlarm(ca)
    t, _ = jalan(tangga, 0.0, 12.0, True)              # sampai tingkat 2
    hasil.append(uji("tingkat 2 tercapai", tangga.tingkat == L2))
    t, catat = jalan(tangga, t, 1.0, True, suara=False)
    hasil.append(uji("speaker mati: langsung tingkat 3 tanpa menunggu 10 dtk",
                     tangga.tingkat == L3 and KIRIM_L3 in catat, f"{catat}"))

    print("\n11. Kantuk sesaat reda sendiri sebelum sempat naik tingkat")
    tangga = TanggaAlarm(ca)
    t, catat = jalan(tangga, 0.0, 4.0, True)
    t, catat = jalan(tangga, t, 2.0, False)
    hasil.append(uji("kembali tenang tanpa perlu tombol",
                     tangga.tingkat == TENANG and SELESAI in catat, f"{catat}"))

    print("\n12. Tombol: aksi hanya saat dilepas, isyarat selagi ditahan")
    def tekan(pola):
        pen = PenafsirTombol(); keluar = []
        for ditekan, t in pola:
            e = pen.perbarui(ditekan, t)
            if e:
                keluar.append(e)
        return keluar
    hasil.append(uji("ketuk 0,3 dtk", tekan([(True, 0.0), (True, 0.3), (False, 0.35)]) == [KETUK]))
    hasil.append(uji("lepas di 2 dtk diabaikan (rentang ambigu)",
                     tekan([(True, 0.0), (True, 2.0), (False, 2.1)]) == []))
    hasil.append(uji("tahan 4 dtk: isyarat lalu aksi saat dilepas",
                     tekan([(True, 0.0), (True, 3.1), (False, 4.0)]) == [ISYARAT_TAHAN, TAHAN]))
    hasil.append(uji("tahan 9 dtk tetap TAHAN -- tombol tidak bisa mematikan Pi",
                     tekan([(True, 0.0), (True, 3.1), (True, 8.1), (False, 9.0)]) == [ISYARAT_TAHAN, TAHAN]))

    print("\n13. GPS: penguraian NMEA dan deteksi kendaraan berhenti")
    u = PenguraiNmea()
    for baris in ("$GPGGA,082754.00,0756.41922,S,11236.69266,E,1,05,1.83,525.2,M,14.6,M,,*43",
                  "$GPRMC,082754.00,A,0756.41922,S,11236.69266,E,0.512,,300826,,,A*79"):
        pos = u.telan(baris, saat=0.0)
    hasil.append(uji("lintang selatan jadi negatif", abs(pos.lat - (-7.940320)) < 1e-5,
                     f"{pos.lat:.6f}"))
    hasil.append(uji("bujur timur tetap positif", abs(pos.lon - 112.611544) < 1e-5,
                     f"{pos.lon:.6f}"))
    hasil.append(uji("knot diubah ke km/jam", abs(pos.kecepatan_kmh - 0.948) < 0.01,
                     f"{pos.kecepatan_kmh:.3f}"))
    hasil.append(uji("satelit & HDOP terbaca", pos.satelit == 5 and abs(pos.hdop - 1.83) < 1e-6,
                     f"{pos.satelit} sat, HDOP {pos.hdop}"))

    u2 = PenguraiNmea()
    kosong = u2.telan("$GPRMC,,V,,,,,,,,,,N*53", saat=0.0)
    hasil.append(uji("kalimat tanpa fix tidak dianggap valid", not kosong.valid))
    rusak = u2.telan("$GPGGA,rusak,,,x", saat=0.0)
    hasil.append(uji("kalimat rusak tidak melempar galat", rusak is not None))

    pb = PantauBerhenti(GpsConfig())
    diam = Posisi(valid=True, kecepatan_kmh=0.4)
    pb.perbarui(diam, 0.0)
    hasil.append(uji("diam 29 detik belum dianggap berhenti", not pb.perbarui(diam, 29.0)))
    hasil.append(uji("diam 31 detik dianggap berhenti", pb.perbarui(diam, 31.0)))
    hasil.append(uji("melaju lagi membatalkan",
                     not pb.perbarui(Posisi(valid=True, kecepatan_kmh=25.0), 32.0)))
    pb2 = PantauBerhenti(GpsConfig())
    pb2.perbarui(Posisi(valid=False), 0.0)
    hasil.append(uji("tanpa fix TIDAK boleh dianggap berhenti",
                     not pb2.perbarui(Posisi(valid=False), 120.0),
                     "sinyal hilang justru saat tidak boleh dipercaya"))

    # --- dashboard & CSV --------------------------------------------------
    print("\n[dashboard, CSV & log kejadian]")
    import csv as _csv
    import io as _io
    import types as _types
    from src.main import _suapi_web
    from src.metrik import KEDIP, MENGUAP, TANPA_WAJAH, TERPEJAM
    from src.web import KeadaanBersama

    # Jumlah sampel kalibrasi harus jumlah frame yang benar-benar terkumpul.
    kal = Kalibrator(2.0)
    t = 0.0
    for i in range(37):                                  # 37 frame dalam 3,6 detik
        kal.tambah(_frame(EAR_BUKA), t)
        if i % 5 == 0:                                   # frame tanpa wajah tidak dihitung
            kal.tambah(HasilDeteksi(ada_wajah=False), t)
        t += 0.1
    hasil.append(uji("sampel kalibrasi = frame aktual (37)",
                     kal.selesai(t) and kal.hasil().sampel == 37,
                     f"sampel={kal.hasil().sampel}"))

    # Log kejadian.
    p = PenilaiKantuk(AmbangConfig(), BASELINE)
    t, _ = jalankan(p, 0.0, 2.0, EAR_BUKA)
    t, _ = jalankan(p, t, 0.15, EAR_TUTUP)               # kedip
    t, _ = jalankan(p, t, 1.0, EAR_BUKA)
    t, _ = jalankan(p, t, 1.5, EAR_TUTUP)                # terpejam 1,5 dtk
    t, _ = jalankan(p, t, 1.0, EAR_BUKA)
    t, _ = jalankan(p, t, 0.4, EAR_BUKA, MAR_NGANGA)     # bicara: tidak dicatat
    t, _ = jalankan(p, t, 0.5, EAR_BUKA)
    t, _ = jalankan(p, t, 1.6, EAR_BUKA, MAR_NGANGA)     # menguap 1,6 dtk
    t, _ = jalankan(p, t, 0.5, EAR_BUKA)
    ev = p.ambil_peristiwa()
    jenis = [e.jenis for e in ev]
    hasil.append(uji("log: kedip, terpejam, menguap tercatat berurutan",
                     jenis == [KEDIP, TERPEJAM, MENGUAP], str(jenis)))
    if jenis == [KEDIP, TERPEJAM, MENGUAP]:
        hasil.append(uji("log: durasi kedip ~0,15 dtk", 0.1 <= ev[0].durasi <= 0.2,
                         f"{ev[0].durasi:.2f}"))
        hasil.append(uji("log: durasi terpejam ~1,5 dtk", 1.4 <= ev[1].durasi <= 1.6,
                         f"{ev[1].durasi:.2f}"))
        hasil.append(uji("log: durasi menguap ~1,6 dtk", 1.5 <= ev[2].durasi <= 1.7,
                         f"{ev[2].durasi:.2f}"))
    hasil.append(uji("log: diambil sekali lalu kosong", p.ambil_peristiwa() == []))
    t, _ = jalankan(p, t, 1.2, EAR_TUTUP)
    p.perbarui(HasilDeteksi(ada_wajah=False), t)
    ev = p.ambil_peristiwa()
    hasil.append(uji("log: terpejam yang terputus wajah hilang tetap dicatat",
                     len(ev) == 1 and ev[0].jenis == TERPEJAM and "terputus" in ev[0].catatan,
                     str([(e.jenis, e.catatan) for e in ev])))

    # Payload web + CSV lewat jalur yang sama dengan loop utama.
    cfg_w = Config()
    web = KeadaanBersama(cfg_w.web)
    gps = _types.SimpleNamespace(posisi=Posisi())
    sesi = Sesi(Kalibrator(2.0), penilai=PenilaiKantuk(AmbangConfig(), BASELINE),
                alarm=TanggaAlarm(AlarmConfig()), mulai=100.0)
    t = 100.0
    for ear, mar, wajah in ([(EAR_BUKA, MAR_TUTUP, True)] * 20       # normal
                            + [(EAR_TUTUP, MAR_TUTUP, True)] * 50    # terpejam 2,5 dtk
                            + [(EAR_BUKA, MAR_TUTUP, True)] * 20
                            + [(0, 0, False)] * 30):                 # wajah hilang
        h = HasilDeteksi(ada_wajah=wajah, ear=ear, mar=mar)
        st = sesi.penilai.perbarui(h, t)
        web.cfg.jeda_sampel_detik = 0.0                              # simpan tiap frame
        _suapi_web(web, None, sesi, st, 20.0, gps, t)
        if st.durasi_tertutup >= 2.0 and "status_kantuk" not in locals():
            status_kantuk = dict(web.status)
        t += LANGKAH
    s = web.status
    hasil.append(uji("payload: MAR raw ikut terkirim", "mar_raw" in s))
    hasil.append(uji("payload: wajah hilang -> status TANPA_WAJAH (bukan AMAN)",
                     s["status_deteksi"] == TANPA_WAJAH and s["level"] == AMAN,
                     s["status_deteksi"]))
    hasil.append(uji("payload: EAR % kosong saat wajah hilang", s["ear"] is None))
    sk = locals().get("status_kantuk", {})
    hasil.append(uji("payload: terpejam lama -> status KANTUK, terpisah dari tingkat alarm",
                     sk.get("status_deteksi") == KANTUK and "tingkat" in sk,
                     f"{sk.get('status_deteksi')} / tingkat {sk.get('tingkat')}"))
    hasil.append(uji("payload: sampel kalibrasi = baseline aktual",
                     s["kalibrasi"]["sampel"] == BASELINE.sampel))
    hasil.append(uji("grafik: titik tanpa wajah ber-EAR null",
                     web.data()["sampel"][-1][1] is None))

    baris = list(_csv.DictReader(_io.StringIO(web.ekspor_csv())))
    wajib = {"timestamp", "session_id", "wajah_terdeteksi", "ear_baseline", "ear_threshold",
             "mar_baseline", "mar_raw", "perclos_siap", "kedip_total", "menguap_total",
             "status", "alasan", "fps", "sampel_kalibrasi", "tingkat_alarm"}
    hasil.append(uji("CSV: semua kolom yang diminta ada",
                     wajib <= set(baris[0]), str(sorted(wajib - set(baris[0])))))
    hasil.append(uji("CSV: satu baris per titik", len(baris) == 120, str(len(baris))))
    hasil.append(uji("CSV: session_id terisi", baris[0]["session_id"] == sesi.id))
    hasil.append(uji("CSV: timestamp ISO berzona", "T" in baris[0]["timestamp"]
                     and baris[0]["timestamp"][-6] in "+-", baris[0]["timestamp"]))
    kantuk = [b for b in baris if b["status"] == KANTUK]
    hasil.append(uji("CSV: baris KANTUK punya alasan", bool(kantuk) and
                     all(b["alasan"] for b in kantuk)))
    hilang = baris[-1]
    hasil.append(uji("CSV: wajah hilang -> status TANPA_WAJAH, ukuran kosong",
                     hilang["status"] == TANPA_WAJAH and hilang["wajah_terdeteksi"] == "0"
                     and hilang["ear_raw"] == "" and hilang["mar_raw"] == ""
                     and hilang["mata"] == "",
                     str({k: hilang[k] for k in ("status", "ear_raw", "mata")})))
    hasil.append(uji("CSV: baseline & sampel kalibrasi tetap terisi saat wajah hilang",
                     float(hilang["ear_baseline"]) == EAR_BUKA
                     and hilang["sampel_kalibrasi"] == str(BASELINE.sampel)))

    ev = list(_csv.DictReader(_io.StringIO(web.ekspor_peristiwa_csv())))
    hasil.append(uji("CSV kejadian: terpejam 2,5 dtk tercatat dengan durasi",
                     any(e["jenis"] == TERPEJAM and 2.4 <= float(e["durasi_detik"]) <= 2.6
                         for e in ev), str([(e["jenis"], e["durasi_detik"]) for e in ev])))
    hasil.append(uji("CSV kejadian: selesai = mulai + durasi",
                     all(e["timestamp_selesai"] >= e["timestamp_mulai"] for e in ev)
                     and bool(ev)))

    lulus = sum(hasil)
    print(f"\n{'=' * 46}\n{lulus}/{len(hasil)} pemeriksaan lulus")
    return 0 if lulus == len(hasil) else 1


if __name__ == "__main__":
    sys.exit(main())
