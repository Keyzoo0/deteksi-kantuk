"""Program utama asisten monitoring rasa kantuk (mata + mulut) berbasis webcam.

Sistem berjalan sebagai tiga keadaan:

    SIAGA      -- sapaan lisan, kamera belum menyala, menunggu tombol ditekan.
    KALIBRASI  -- kamera menyala; selama wajah belum masuk bingkai pengguna
                  dituntun suara. Begitu wajah terlihat, instruksi kalibrasi
                  diucapkan lalu baseline EAR/MAR direkam.
    MONITOR    -- penilaian kantuk tiap frame + peringatan lisan. Bila wajah
                  hilang lebih dari `mati_tanpa_wajah_detik`, sistem mati
                  sendiri dan kembali ke SIAGA (ketuk tombol untuk mulai lagi).

Jalankan:  python -m src.main            (dari folder project)
Tombol fisik : ketuk = matikan alarm | tahan 3 dtk = nyalakan/matikan sistem |
               tahan 8 dtk = matikan Raspberry Pi
Papan ketik  : spasi = ketuk | c = tahan 3 dtk | q keluar | d landmark

Menyalakan sistem selalu diawali kalibrasi, jadi mematikan lalu menyalakan
lagi sekaligus berfungsi sebagai kalibrasi ulang -- tidak perlu tombol sendiri.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from .config import Config
from .deteksi import DetektorWajah
from .gps import PembacaGps, Posisi
from .kamera import (buka_kamera, cari_perangkat, info_kamera, pastikan_kamera_ada,
                     perangkat_merek, sambung_ulang)
from .metrik import KANTUK, Kalibrator, PenilaiKantuk, Status
from .notifikasi import Notifikasi
from .senyap import redam_pustaka_c, redam_stderr, siapkan_font_qt
from .alarm import (AKUI, BUNYI_L1, BUNYI_L2, KIRIM_L3, MENEPI, MULAI_L2, SELESAI,
                    L2, TENANG, TanggaAlarm)
from .suara import (ARAHKAN, BERHENTI, BIP, BIP_GANDA, DIAKUI, ISTIRAHAT, MATI,
                    MENGANTUK, MULAI_KALIBRASI, SALAM, SIAP, SIRENE, TEKAN_TOMBOL,
                    TERKIRIM, AsistenSuara)
from .tampilan import gambar_kalibrasi, gambar_overlay, layar_siaga
from .web import Cuplikan, KeadaanBersama, mulai_server
from .tombol_gpio import (ISYARAT_TAHAN, ISYARAT_TAHAN_LAMA, KEDIP_CEPAT,
                          KEDIP_LAMBAT, KETUK, NYALA, PADAM, TAHAN, TAHAN_LAMA,
                          TombolFisik)

AKAR = Path(__file__).resolve().parent.parent
JUDUL = "Deteksi Rasa Kantuk"
SIAGA, KALIBRASI, MONITOR = "siaga", "kalibrasi", "monitor"
SPASI, ESC = 32, 27


def argumen() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="deteksi-kantuk",
        description="Asisten monitoring rasa kantuk dari mata (EAR/PERCLOS) dan mulut.",
    )
    p.add_argument("--config", default=str(AKAR / "config.json"),
                   help="berkas konfigurasi JSON (default: config.json)")
    p.add_argument("--sumber", help="index webcam (0/1) atau path file video")
    p.add_argument("--merek", help="hanya pakai kamera merek ini (default: logitech; "
                                   "kosongkan dengan --merek '' untuk menerima semua)")
    p.add_argument("--kalibrasi", type=float, help="durasi kalibrasi dalam detik")
    p.add_argument("--tanpa-suara", action="store_true",
                   help="matikan asisten suara (peringatan lisan lewat speaker)")
    p.add_argument("--langsung", action="store_true",
                   help="lewati layar siaga: sistem langsung menyala tanpa tombol")
    p.add_argument("--tanpa-jendela", action="store_true",
                   help="mode headless: status dicetak ke terminal, tanpa imshow")
    p.add_argument("--debug", action="store_true", help="gambar seluruh 478 landmark")
    p.add_argument("--rekam", metavar="BERKAS",
                   help="simpan video hasil anotasi (mis. hasil/anotasi.mp4)")
    p.add_argument("--verbose", action="store_true",
                   help="tampilkan pesan bawaan OpenCV/MediaPipe (mis. Corrupt JPEG)")
    return p.parse_args()


@dataclass
class Sesi:
    """Satu kali sistem dinyalakan: dari kalibrasi sampai dimatikan."""

    kalibrator: Kalibrator
    penilai: PenilaiKantuk | None = None
    episode: list[dict] = field(default_factory=list)   # riwayat periode KANTUK
    level_lalu: str | None = None
    frame: int = 0
    mulai: float = 0.0                   # waktu monitoring mulai (untuk ringkasan)
    t_akhir: float = 0.0
    diumumkan: bool = False              # instruksi kalibrasi sudah diucapkan
    hilang_sejak: float | None = None    # kapan wajah mulai tidak terlihat
    alarm: TanggaAlarm | None = None     # tangga alarm 3 tingkat
    alarm_bunyi: bool = False            # sirene tingkat 2 sedang berbunyi
    l3_terkirim: bool = False            # notifikasi darurat sudah dikirim


def cetak_status(st: Status, fps: float, catatan: str = "",
                 posisi: Posisi | None = None) -> None:
    """Baris status untuk mode headless (menimpa baris yang sama)."""
    tanda = "!!" if st.level == KANTUK else "  "
    alasan = ", ".join(st.alasan) or ("-" if st.ada_wajah else "wajah hilang")
    if posisi is not None:
        alasan = (f"{posisi.kecepatan_kmh:4.1f} km/jam | {alasan}" if posisi.valid
                  else f"GPS {posisi.satelit}sat | {alasan}")
    if catatan:
        alasan = f"{alasan} | {catatan}"
    sys.stdout.write(
        f"\r{tanda} {st.level:<6} | EAR {st.ear_norm * 100:3.0f}% | "
        f"MAR {st.mar:4.2f}/{st.ambang_mar:.2f} | PERCLOS {st.perclos * 100:3.0f}%{'' if st.perclos_matang else '?'} | "
        f"kedip {st.kedip_total:3d} | menguap {st.menguap_total:2d} | "
        f"{fps:4.1f} fps | {alasan:<52}"
    )
    sys.stdout.flush()


def main() -> int:
    arg = argumen()
    if arg.verbose:
        return _jalankan(arg)
    # Pesan pustaka C diredam supaya keluaran program terbaca; galat Python
    # tetap muncul seperti biasa.
    with redam_pustaka_c():
        return _jalankan(arg)


def _jalankan(arg: argparse.Namespace) -> int:
    cfg = Config.muat(arg.config)
    if arg.sumber:
        cfg.kamera.sumber = arg.sumber
    if arg.merek is not None:
        cfg.kamera.merek = arg.merek
    if arg.kalibrasi:
        cfg.kalibrasi_detik = arg.kalibrasi
    if arg.tanpa_suara:
        cfg.suara.aktif = False
    tampilkan = cfg.tampilkan_jendela and not arg.tanpa_jendela
    # Sumber berupa berkas video diperlakukan berbeda dari webcam: waktunya
    # diambil dari timeline video, bukan jam dinding, supaya durasi kalibrasi
    # dan jendela PERCLOS tetap benar walau pemrosesan lebih cepat/lambat
    # daripada waktu nyata. Efek cermin juga tidak dipakai.
    sumber = str(cfg.kamera.sumber).strip().lower()
    dari_berkas = not (sumber == "auto" or sumber.lstrip("-").isdigit())
    if dari_berkas:
        cfg.kamera.flip_horizontal = False

    print("=" * 62)
    print(" ASISTEN MONITORING RASA KANTUK - MediaPipe + EAR/PERCLOS/MAR")
    print("=" * 62)

    # Kamera diperiksa sebelum model dimuat: bila perangkatnya tidak ada,
    # program berhenti tanpa meninggalkan objek MediaPipe yang belum ditutup
    # (pembersihannya saat interpreter mati memunculkan traceback
    # "Exception ignored in ... FaceLandmarker.__del__").
    if not dari_berkas:
        try:
            pastikan_kamera_ada(cfg.kamera)
        except RuntimeError as e:
            print(f"\n{e}")
            return 2
    if tampilkan:
        siapkan_font_qt()

    detektor = DetektorWajah()
    asisten = AsistenSuara(cfg.suara, AKAR)
    if dari_berkas:
        print(f"Kamera   : berkas {cfg.kamera.sumber}")
    else:
        # Nomor index di config hanya pilihan pertama; yang benar-benar dipakai
        # baru diketahui saat kamera dibuka, jadi di sini yang ditampilkan
        # adalah kandidat yang memang terpasang.
        calon = perangkat_merek(cfg.kamera.merek)
        print(f"Kamera   : {', '.join(p.label() for p in calon) or '(tidak ada)'}")
    print(f"Suara    : {asisten.keterangan}")
    if asisten.aktif:
        print(f"           kantuk: terpejam >{cfg.suara.terpejam_detik:.0f} detik atau "
              f"menguap >{cfg.suara.menguap_detik:.0f} detik | "
              f"wajah hilang >{cfg.suara.wajah_hilang_detik:.0f} detik "
              f"(diulang tiap {cfg.suara.jeda_ulang_detik:.0f} detik)")
    print(f"Kalibrasi: {cfg.kalibrasi_detik:.0f} detik setelah wajah terlihat")
    print(f"Mati auto: wajah hilang >{cfg.mati_tanpa_wajah_detik:.0f} detik saat monitoring")
    print(f"Mode     : {'jendela OpenCV' if tampilkan else 'headless (terminal)'}")
    print("Tombol   : ketuk = matikan alarm | tahan 3 dtk = nyalakan/matikan "
          "sistem | tahan 8 dtk = matikan Pi\n")

    tombol = TombolFisik(cfg.tombol)
    print(f"Tombol   : {tombol.keterangan}")
    gps = PembacaGps(cfg.gps)
    print(f"GPS      : {gps.keterangan}")
    notif = Notifikasi(cfg.notifikasi, AKAR)
    print(f"Kerabat  : {notif.keterangan}")
    keadaan_web = KeadaanBersama(cfg.web)
    server, ket_web = mulai_server(keadaan_web)
    if server is not None:
        import socket

        from .sistem import info_sistem
        # Nama mDNS didahulukan: alamat IP berubah tiap pindah jaringan,
        # sedangkan <nama-host>.local tetap sama di mana pun alat dipasang.
        alamat = [f"{socket.gethostname()}.local"] + info_sistem().get("alamat", "").split()
        ket_web = " | ".join(f"http://{a}:{cfg.web.port}" for a in alamat) or ket_web
    print(f"Web      : {ket_web}")
    # Tanpa tombol fisik maupun jendela (mis. dijalankan systemd di Pi yang
    # tombolnya belum terpasang) tidak ada cara menekan apa pun, jadi sistem
    # langsung menyala. Sumber berkas video juga tidak perlu ditunggu.
    auto = arg.langsung or dari_berkas or (not tampilkan and not tombol.ada)
    try:
        return _loop(arg, cfg, detektor, asisten, tombol, gps, notif, keadaan_web,
                     tampilkan, dari_berkas, auto)
    finally:
        tombol.tutup()
        gps.tutup()
        notif.tutup()
        if server is not None:
            server.shutdown()


def _loop(arg, cfg: Config, detektor: DetektorWajah, asisten: AsistenSuara,
          tombol: TombolFisik, gps: PembacaGps, notif: Notifikasi,
          web: KeadaanBersama, tampilkan: bool, dari_berkas: bool,
          auto: bool) -> int:
    keadaan = SIAGA
    cap: cv2.VideoCapture | None = None
    sesi: Sesi | None = None
    perekam: cv2.VideoWriter | None = None
    jendela_dibuat = False
    debug = arg.debug
    fps = 0.0
    t_lalu = time.monotonic()
    cetak_terakhir = 0.0
    gagal_baca = 0
    fps_berkas = 25.0
    kode = 0
    salam_diucapkan = False

    def tampilkan_frame(frame) -> int:
        """Tampilkan frame (bila ada jendela) dan kembalikan tombol papan ketik."""
        nonlocal jendela_dibuat
        if not tampilkan:
            return -1
        if jendela_dibuat:
            cv2.imshow(JUDUL, frame)
        else:
            # Pembuatan jendela pertama memicu beberapa pesan Qt/X11 yang tidak
            # ada hubungannya dengan program.
            with redam_stderr():
                cv2.imshow(JUDUL, frame)
            jendela_dibuat = True
        return cv2.waitKey(1) & 0xFF

    def isyarat(pesan: str) -> None:
        """Bunyi pendek penanda ambang tahanan tercapai.

        Suara yang sedang berjalan sengaja dipotong: alat ini tidak punya
        layar maupun LED yang pasti terpasang, jadi bip inilah satu-satunya
        cara pengendara tahu tahanannya sudah cukup. Tanpa ini dia akan
        menahan terus dan tanpa sadar memicu ambang berikutnya.
        """
        asisten.diam()
        asisten.ucap(pesan, paksa=True)

    def baca_tombol(frame, t: float) -> str | None:
        """Satu peristiwa tombol, dari GPIO maupun papan ketik (untuk uji)."""
        kunci = tampilkan_frame(frame)
        if kunci in (ord("q"), ESC):
            return "keluar"
        if kunci == SPASI:
            return KETUK
        if kunci == ord("c"):
            return TAHAN
        if kunci == ord("d"):
            return "debug"
        return tombol.periksa(t)

    def nyalakan() -> bool:
        """Buka kamera dan mulai sesi baru. False bila kameranya tidak ada."""
        nonlocal cap, sesi, keadaan, fps_berkas, gagal_baca, t_lalu
        try:
            cap = buka_kamera(cfg.kamera)
        except RuntimeError as e:
            print(f"\n{e}\n")
            return False
        fps_berkas = cap.get(cv2.CAP_PROP_FPS) or 25.0
        gagal_baca = 0
        t_lalu = time.monotonic()
        sesi = Sesi(Kalibrator(cfg.kalibrasi_detik), alarm=TanggaAlarm(cfg.alarm))
        keadaan = KALIBRASI
        # Sumber berkas tidak punya perangkat untuk dicari namanya.
        asal = (f"berkas {cfg.kamera.sumber}" if dari_berkas
                else cari_perangkat(int(cfg.kamera.sumber)).label())
        print(f"\n[sistem] menyala -- {asal} -> {info_kamera(cap)}")
        return True

    def matikan(alasan: str, sapa_lagi: bool = True) -> None:
        """Akhiri sesi: cetak ringkasan, lepas kamera, kembali ke layar siaga."""
        nonlocal cap, sesi, keadaan, salam_diucapkan
        print(f"\n[sistem] {alasan}")
        if sesi is not None and sesi.penilai is not None:
            _cetak_ringkasan(sesi, arg.rekam)
        if cap is not None:
            cap.release()
            cap = None
        sesi = None
        keadaan = SIAGA
        # Sapaan panjang tidak diulang kalau pengguna sendiri yang mematikan:
        # dia baru saja mendengar "sistem dimatikan, silakan beristirahat".
        salam_diucapkan = not sapa_lagi
        tombol.pola_led(KEDIP_LAMBAT)

    try:
        while True:
            asisten.layani()

            # --- SIAGA: kamera mati, menunggu tombol ---------------------
            if keadaan == SIAGA:
                if auto:
                    if not nyalakan():
                        kode = 2
                        break
                    continue
                if not salam_diucapkan:
                    asisten.ucap(SALAM, antre=True, paksa=True)
                    tombol.pola_led(KEDIP_LAMBAT)
                    salam_diucapkan = True
                    if not tampilkan:
                        sys.stdout.write("\r  SIAGA -- tahan tombol 3 detik untuk memulai"
                                         "        ")
                        sys.stdout.flush()
                bingkai_siaga = layar_siaga(cfg.kamera.lebar, cfg.kamera.tinggi,
                                            "Tahan tombol 3 detik untuk memulai")
                # Halaman web tetap menampilkan sesuatu saat sistem siaga,
                # supaya jelas bedanya "belum dinyalakan" dengan "rusak".
                web.perbarui(bingkai_siaga, {"keadaan": "siaga"}, None, time.monotonic())
                peristiwa = baca_tombol(bingkai_siaga, time.monotonic())
                if peristiwa == "keluar":
                    break
                if peristiwa == TAHAN_LAMA:
                    _matikan_pi(asisten)
                    break
                if peristiwa == ISYARAT_TAHAN:
                    tombol.pola_led(KEDIP_CEPAT)
                    isyarat(BIP)
                if peristiwa == ISYARAT_TAHAN_LAMA:
                    isyarat(BIP_GANDA)
                if peristiwa == TAHAN:
                    asisten.diam()          # potong sapaan, langsung bekerja
                    if not nyalakan():
                        salam_diucapkan = False
                        continue
                elif not tampilkan:
                    time.sleep(0.05)        # tanpa jendela, jangan sibuk 100% CPU
                continue

            assert cap is not None and sesi is not None

            # --- baca frame ----------------------------------------------
            ok, frame = cap.read()
            if not ok:
                if dari_berkas:
                    print("\nVideo selesai.")
                    break
                gagal_baca += 1
                if gagal_baca > 20:
                    # Bukan sekadar frame lompat: kemungkinan besar perangkatnya
                    # lepas dari bus USB. Coba sambungkan lagi tanpa kehilangan
                    # hasil kalibrasi maupun hitungan PERCLOS.
                    print("\n[kamera] aliran frame terputus, mencoba menyambung ulang...")
                    cap = sambung_ulang(cap, cfg.kamera)
                    if cap is None:
                        matikan(f"kamera {cfg.kamera.merek or ''} tidak kembali, "
                                "sistem dimatikan.")
                        continue
                    gagal_baca = 0
                time.sleep(0.03)
                continue
            gagal_baca = 0

            if cfg.kamera.flip_horizontal:
                frame = cv2.flip(frame, 1)

            sesi.frame += 1
            if dari_berkas:
                posisi = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                # Sebagian berkas tidak melaporkan posisi; pakai nomor frame.
                t = posisi if posisi > 0 else sesi.frame / max(1.0, fps_berkas)
            else:
                t = time.monotonic()
            hasil = detektor.proses(frame, int(t * 1000))

            dt = t - t_lalu
            t_lalu = t
            sesi.t_akhir = t
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt

            if perekam is None and arg.rekam:
                perekam = _buat_perekam(arg.rekam, cap, fps_berkas)

            # Tanpa internet, alarm tingkat 3 tidak akan sampai ke kerabat.
            # Pengendara harus tahu, jadi diingatkan berkala selama sistem
            # menyala -- tetapi tidak sampai menimpa bunyi alarm yang sedang
            # berlangsung (antre=False).
            if notif.siap and not notif.daring:
                asisten.ucap(TANPA_INTERNET,
                             jeda=cfg.suara.jeda_tanpa_internet_detik)

            catatan = ""
            # --- KALIBRASI -----------------------------------------------
            if keadaan == KALIBRASI:
                web.perbarui(frame, {"keadaan": "kalibrasi",
                                     "sisa": round(sesi.kalibrator.sisa_detik(t), 1)},
                             None, t)
                catatan = _tahap_kalibrasi(cfg, sesi, asisten, hasil, t)
                if sesi.penilai is not None:
                    keadaan = MONITOR
                if tampilkan or perekam is not None or web.ada_penonton:
                    gambar_kalibrasi(frame, hasil, sesi.kalibrator.sisa_detik(t))
                if not tampilkan and t - cetak_terakhir > 0.5:
                    sisa = sesi.kalibrator.sisa_detik(t)
                    pesan = (f"kalibrasi {sisa:.1f} detik lagi" if sesi.kalibrator.dimulai
                             else "menunggu wajah terdeteksi")
                    sys.stdout.write(f"\r  {pesan:<44}")
                    sys.stdout.flush()
                    cetak_terakhir = t

            # --- MONITOR --------------------------------------------------
            else:
                st = sesi.penilai.perbarui(hasil, t)      # type: ignore[union-attr]
                _catat_episode(sesi, st, t, gps.posisi, web)
                habis, catatan = _tahap_monitor(cfg, sesi, asisten, st, t, dari_berkas)
                _bunyikan_alarm(cfg, sesi, asisten, tombol, gps, notif, st, t, frame)
                if habis:
                    matikan(f"wajah hilang lebih dari "
                            f"{cfg.mati_tanpa_wajah_detik:.0f} detik, sistem dimatikan.")
                    continue
                if tampilkan or perekam is not None or web.ada_penonton:
                    gambar_overlay(frame, hasil, st, fps, debug,
                                   asisten.sedang_bicara, catatan)
                _suapi_web(web, frame, sesi, st, fps, gps, t)
                if not tampilkan and t - cetak_terakhir > 0.2:
                    cetak_status(st, fps, catatan, gps.posisi)
                    cetak_terakhir = t

            if perekam is not None:
                perekam.write(frame)

            peristiwa = baca_tombol(frame, t)
            if peristiwa == "keluar":
                break
            elif peristiwa == "debug":
                debug = not debug
            elif peristiwa == KETUK:
                # Selagi alarm berbunyi, ketukan berarti "saya sadar" dan itu
                # satu-satunya cara mematikan alarm tingkat 2 ke atas.
                if sesi.alarm.tingkat:
                    print(f"\n[alarm] tombol ditekan pada tingkat "
                          f"{sesi.alarm.tingkat} -- alarm dimatikan")
                for e in sesi.alarm.ketuk(t):
                    _mainkan(asisten, e)
                    _tutup_laporan(sesi, notif, gps, "pengendara menekan tombol")
                sesi.alarm_bunyi = False
            elif peristiwa == ISYARAT_TAHAN:
                tombol.pola_led(KEDIP_CEPAT)
                isyarat(BIP)
            elif peristiwa == ISYARAT_TAHAN_LAMA:
                isyarat(BIP_GANDA)
            elif peristiwa == TAHAN:
                # Pengendara ingin berhenti/istirahat. Kamera dilepas dan
                # sistem kembali siaga; menyalakannya lagi otomatis mengulang
                # kalibrasi, jadi tidak ada tombol kalibrasi tersendiri.
                asisten.ucap(ISTIRAHAT, antre=True, paksa=True)
                matikan("tombol ditahan -- sistem dimatikan untuk istirahat.",
                        sapa_lagi=False)
                continue
            elif peristiwa == TAHAN_LAMA:
                _matikan_pi(asisten)
                break
    except KeyboardInterrupt:
        print("\nDihentikan pengguna.")
    finally:
        asisten.tutup()
        if cap is not None:
            cap.release()
        detektor.tutup()
        if perekam is not None:
            perekam.release()
        if tampilkan:
            cv2.destroyAllWindows()
        if sesi is not None and sesi.penilai is not None:
            _cetak_ringkasan(sesi, arg.rekam)
    return kode


def _tahap_kalibrasi(cfg: Config, sesi: Sesi, asisten: AsistenSuara,
                     hasil, t: float) -> str:
    """Tuntun pengguna sampai baseline EAR/MAR terekam. Kembalikan catatan layar."""
    if not hasil.ada_wajah:
        if sesi.hilang_sejak is None:
            sesi.hilang_sejak = t
        if t - sesi.hilang_sejak >= cfg.suara.wajah_hilang_detik:
            asisten.ucap(ARAHKAN)
        return ""

    sesi.hilang_sejak = None
    if not sesi.diumumkan:
        # Wajah baru saja masuk bingkai: instruksinya diucapkan lebih dulu,
        # baru baseline direkam -- percuma mengukur selagi pengguna masih
        # mendengarkan "arahkan dan tahan wajah Anda".
        asisten.ucap(MULAI_KALIBRASI, antre=True, paksa=True)
        sesi.diumumkan = True
    if asisten.sedang_bicara:
        return "menunggu instruksi selesai"

    sesi.kalibrator.tambah(hasil, t)
    if sesi.kalibrator.selesai(t):
        baseline = sesi.kalibrator.hasil()
        sesi.penilai = PenilaiKantuk(cfg.ambang, baseline)
        sesi.mulai = t
        asisten.ucap(SIAP, antre=True, paksa=True)
        print(f"\nBaseline : EAR {baseline.ear:.3f} | MAR {baseline.mar:.3f} "
              f"({baseline.sampel} frame) -- monitoring dimulai\n")
    return ""


def _tahap_monitor(cfg: Config, sesi: Sesi, asisten: AsistenSuara, st: Status,
                   t: float, dari_berkas: bool) -> tuple[bool, str]:
    """Peringatan lisan + pengawasan wajah. Kembalikan (sistem_harus_mati, catatan)."""
    if st.ada_wajah:
        sesi.hilang_sejak = None
        # Ambang suara lebih longgar daripada ambang tulisan KANTUK di layar:
        # peringatan lisan baru berbunyi kalau kondisinya sudah meyakinkan.
        if (st.durasi_tertutup >= cfg.suara.terpejam_detik
                or st.durasi_menguap >= cfg.suara.menguap_detik):
            asisten.ucap(MENGANTUK)
        return False, ""

    if sesi.hilang_sejak is None:
        sesi.hilang_sejak = t
    lama = t - sesi.hilang_sejak
    if lama >= cfg.suara.wajah_hilang_detik:
        asisten.ucap(ARAHKAN)
    # Berkas video tidak dimatikan otomatis: analisis harus jalan sampai habis.
    if not dari_berkas and lama >= cfg.mati_tanpa_wajah_detik:
        asisten.ucap(MATI, antre=True, paksa=True)
        return True, ""
    sisa = cfg.mati_tanpa_wajah_detik - lama
    if not dari_berkas and lama >= cfg.suara.wajah_hilang_detik:
        return False, f"MATI DALAM {sisa:.0f} DETIK"
    return False, ""


# Peristiwa tangga alarm -> pesan yang dibunyikan. Sirene dan "tekan tombol"
# diantre berpasangan supaya nada peringatan selalu diikuti instruksinya.
_SUARA_ALARM = {
    BUNYI_L1: (MENGANTUK,),
    MULAI_L2: (SIRENE, TEKAN_TOMBOL),
    BUNYI_L2: (SIRENE, TEKAN_TOMBOL),
    KIRIM_L3: (TERKIRIM,),
    AKUI: (DIAKUI,),
    MENEPI: (BERHENTI,),
    SELESAI: (),
}


def _mainkan(asisten: AsistenSuara, peristiwa: str) -> None:
    for pesan in _SUARA_ALARM.get(peristiwa, ()):
        asisten.ucap(pesan, antre=True, paksa=True)


def _suapi_web(web: KeadaanBersama, frame, sesi: Sesi, st: Status, fps: float,
               gps: PembacaGps, t: float) -> None:
    """Titipkan frame + metrik terbaru ke web server (tanpa memblokir)."""
    posisi = gps.posisi
    tingkat = sesi.alarm.tingkat if sesi.alarm else 0
    web.perbarui(frame, {
        "keadaan": "monitor",
        "level": st.level,
        "alasan": ", ".join(st.alasan),
        "ear": st.ear_norm * 100,
        "perclos": st.perclos * 100,
        "kedip": st.kedip_total,
        "menguap": st.menguap_total,
        "tingkat": tingkat,
        "fps": fps,
        "gps": (f"{posisi.kecepatan_kmh:.0f} km/jam" if posisi.valid
                else f"{posisi.satelit} sat"),
    }, Cuplikan(t - sesi.mulai, st.ear_norm * 100, st.perclos * 100, tingkat), t)


def _pesan_darurat(sesi: Sesi, st: Status, gps: PembacaGps) -> str:
    posisi = gps.posisi
    baris = [
        "PERINGATAN KANTUK",
        "Pengendara terdeteksi mengantuk dan tidak merespons alarm.",
        "",
        f"Waktu    : {time.strftime('%d %b %Y %H:%M:%S %Z')}",
        f"Alasan   : {', '.join(st.alasan) or 'mata terpejam lama'}",
        f"Kejadian : ke-{sesi.alarm.kejadian_l3} dalam perjalanan ini",  # type: ignore[union-attr]
    ]
    if posisi.valid:
        baris += [f"Kecepatan: {posisi.kecepatan_kmh:.0f} km/jam",
                  f"Posisi   : {posisi.lat:.6f}, {posisi.lon:.6f}",
                  posisi.tautan]
    else:
        baris.append("Posisi   : belum dapat sinyal GPS")
    return "\n".join(baris)


def _tutup_laporan(sesi: Sesi, notif: Notifikasi, gps: PembacaGps, sebab: str) -> None:
    """Kabari kerabat bahwa keadaan sudah selesai.

    Tanpa pesan penutup, kerabat hanya menerima kabar buruk lalu senyap -- itu
    membuat panik dan tidak berguna. Pesan ini yang mengubahnya jadi informasi.
    """
    if not sesi.l3_terkirim:
        return
    sesi.l3_terkirim = False
    posisi = gps.posisi
    teks = [f"Situasi selesai: {sebab}.",
            f"Waktu    : {time.strftime('%d %b %Y %H:%M:%S %Z')}"]
    if posisi.valid:
        teks += [f"Posisi   : {posisi.tautan}"]
    notif.kirim("\n".join(teks))


def _bunyikan_alarm(cfg: Config, sesi: Sesi, asisten: AsistenSuara,
                    tombol: TombolFisik, gps: PembacaGps, notif: Notifikasi,
                    st: Status, t: float, frame=None) -> None:
    """Jalankan tangga alarm satu langkah dan wujudkan hasilnya jadi suara/LED."""
    assert sesi.alarm is not None
    # Dipanggil tiap frame supaya hitungan "sudah diam berapa lama" tetap
    # berjalan walau alarm belum berbunyi.
    if gps.berhenti(t) and sesi.alarm.tingkat:
        print(f"\n[alarm] kendaraan berhenti -- alarm tingkat "
              f"{sesi.alarm.tingkat} dimatikan")
        for e in sesi.alarm.kendaraan_berhenti(t):
            _mainkan(asisten, e)
            _tutup_laporan(sesi, notif, gps, "kendaraan sudah berhenti")
    mengantuk = st.ada_wajah and (
        st.durasi_tertutup >= cfg.suara.terpejam_detik
        or st.durasi_menguap >= cfg.suara.menguap_detik)
    sebelum = sesi.alarm.tingkat
    for e in sesi.alarm.perbarui(mengantuk, t, asisten.perangkat_hidup()):
        if e == KIRIM_L3:
            foto = None
            if frame is not None and cfg.notifikasi.kirim_foto:
                # Foto hanya disertakan pada tingkat 3, sesuai kesepakatan:
                # kejadian biasa cukup teks, yang darurat perlu bukti keadaan.
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                foto = buf.tobytes() if ok else None
            dikirim = notif.kirim(_pesan_darurat(sesi, st, gps), foto)
            sesi.l3_terkirim = sesi.l3_terkirim or dikirim
            print(f"\n[alarm] TINGKAT 3 -- notifikasi kerabat "
                  f"{'dikirim' if dikirim else 'GAGAL (' + notif.keterangan + ')'}")
        _mainkan(asisten, e)
    if sesi.alarm.tingkat != sebelum:
        print(f"\n[alarm] tingkat {sebelum} -> {sesi.alarm.tingkat}")
    sesi.alarm_bunyi = sesi.alarm.tingkat >= L2
    tombol.pola_led(KEDIP_CEPAT if sesi.alarm.tingkat >= L2
                    else (NYALA if sesi.alarm.tingkat == TENANG else KEDIP_LAMBAT))


def _matikan_pi(asisten: AsistenSuara) -> None:
    """Matikan Raspberry Pi dengan aman (tombol ditahan 8 detik)."""
    import subprocess
    print("\n[sistem] tombol ditahan lama -- mematikan Raspberry Pi...")
    asisten.ucap(MATI, antre=True, paksa=True)
    for _ in range(60):                    # biarkan pesannya selesai berbunyi
        if not asisten.sedang_bicara:
            break
        time.sleep(0.1)
    for perintah in (["sudo", "-n", "poweroff"], ["systemctl", "poweroff"]):
        try:
            if subprocess.run(perintah, timeout=10).returncode == 0:
                return
        except (OSError, subprocess.SubprocessError):
            continue
    print("[sistem] gagal mematikan otomatis; matikan manual lewat SSH.")


def _catat_episode(sesi: Sesi, st: Status, t: float,
                   posisi: Posisi | None = None,
                   web: KeadaanBersama | None = None) -> None:
    """Catat awal & akhir tiap periode KANTUK untuk ringkasan sesi."""
    # Waktu dicatat relatif terhadap awal monitoring supaya terbaca sebagai
    # menit:detik sesi, bukan angka jam monotonic sistem.
    lewat = t - sesi.mulai
    if st.level != sesi.level_lalu:
        if st.level == KANTUK:
            sesi.episode.append({"mulai": lewat, "selesai": lewat,
                                 "alasan": list(st.alasan),
                                 "posisi": posisi})
            if web is not None:
                web.catat_kejadian({
                    "jam": time.strftime("%H:%M:%S"),
                    "lama": "berlangsung",
                    "alasan": ", ".join(st.alasan),
                    "tautan": posisi.tautan if posisi and posisi.valid else "",
                })
        sesi.level_lalu = st.level
    elif st.level == KANTUK and sesi.episode:
        sesi.episode[-1]["selesai"] = lewat
        if web is not None and web.riwayat:
            web.riwayat[-1]["lama"] = f"{lewat - sesi.episode[-1]['mulai']:.1f} dtk"
        for a in st.alasan:
            pokok = a.split(" ")[0]
            if not any(x.startswith(pokok) for x in sesi.episode[-1]["alasan"]):
                sesi.episode[-1]["alasan"].append(a)


def _buat_perekam(berkas: str, cap: cv2.VideoCapture, fps: float) -> cv2.VideoWriter:
    Path(berkas).parent.mkdir(parents=True, exist_ok=True)
    # Codec mengikuti ekstensi. .webm (VP8) bisa langsung diputar peramban
    # tanpa memasang codec apa pun; .mp4 di sini memakai MPEG-4 Part 2 karena
    # wheel OpenCV tidak membawa encoder H.264.
    kode = {"webm": "VP80", "avi": "XVID"}.get(
        Path(berkas).suffix.lstrip(".").lower(), "mp4v")
    perekam = cv2.VideoWriter(
        berkas, cv2.VideoWriter_fourcc(*kode), fps,
        (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))
    if not perekam.isOpened():
        raise RuntimeError(f"Tidak bisa membuat berkas rekaman '{berkas}' (codec {kode}).")
    print(f"Rekam    : {berkas} (codec {kode})")
    return perekam


def _cetak_ringkasan(sesi: Sesi, rekam: str | None) -> None:
    penilai = sesi.penilai
    assert penilai is not None
    print("\n" + "=" * 62)
    print(" RINGKASAN SESI")
    print("=" * 62)
    print(f"Frame diproses  : {sesi.frame}")
    print(f"Kedipan         : {penilai.kedip_total}")
    print(f"Menguap         : {penilai.menguap_total}")
    print(f"Periode KANTUK  : {len(sesi.episode)}")

    for i, e in enumerate(sesi.episode, 1):
        lama = e["selesai"] - e["mulai"]
        print(f"  {i}. {_jam(e['mulai'])} - {_jam(e['selesai'])} "
              f"({lama:.1f} detik) : {', '.join(e['alasan'])}")
        pos = e.get("posisi")
        if pos is not None and pos.valid:
            print(f"      {pos.tautan}")
    if rekam:
        print(f"\nVideo anotasi   : {rekam}")


def _jam(detik: float) -> str:
    return f"{int(detik) // 60:02d}:{detik % 60:05.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
