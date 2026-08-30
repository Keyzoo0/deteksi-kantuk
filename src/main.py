"""Program utama asisten monitoring rasa kantuk (mata + mulut) berbasis webcam.

Sistem berjalan sebagai tiga keadaan:

    SIAGA      -- sapaan lisan, kamera belum menyala, menunggu tombol SPASI.
    KALIBRASI  -- kamera menyala; selama wajah belum masuk bingkai pengguna
                  dituntun suara. Begitu wajah terlihat, instruksi kalibrasi
                  diucapkan lalu baseline EAR/MAR direkam.
    MONITOR    -- penilaian kantuk tiap frame + peringatan lisan. Bila wajah
                  hilang lebih dari `mati_tanpa_wajah_detik`, sistem mati
                  sendiri dan kembali ke SIAGA (tekan SPASI untuk mulai lagi).

Jalankan:  python -m src.main            (dari folder project)
Tombol  :  spasi mulai | q keluar | c kalibrasi ulang | d tampilkan landmark
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
from .kamera import (buka_kamera, cari_perangkat, info_kamera, pastikan_kamera_ada,
                     sambung_ulang)
from .metrik import KANTUK, Kalibrator, PenilaiKantuk, Status
from .senyap import redam_pustaka_c, redam_stderr, siapkan_font_qt
from .suara import (ARAHKAN, MATI, MENGANTUK, MULAI_KALIBRASI, SALAM, SIAP,
                    AsistenSuara)
from .tampilan import gambar_kalibrasi, gambar_overlay, layar_siaga
from .tombol import PembacaTombol

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


def cetak_status(st: Status, fps: float, catatan: str = "") -> None:
    """Baris status untuk mode headless (menimpa baris yang sama)."""
    tanda = "!!" if st.level == KANTUK else "  "
    alasan = ", ".join(st.alasan) or ("-" if st.ada_wajah else "wajah hilang")
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
    dari_berkas = not str(cfg.kamera.sumber).isdigit()
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
    print(f"Kamera   : {cari_perangkat(int(cfg.kamera.sumber)).label() if not dari_berkas else cfg.kamera.sumber}")
    print(f"Suara    : {asisten.keterangan}")
    if asisten.aktif:
        print(f"           kantuk: terpejam >{cfg.suara.terpejam_detik:.0f} detik atau "
              f"menguap >{cfg.suara.menguap_detik:.0f} detik | "
              f"wajah hilang >{cfg.suara.wajah_hilang_detik:.0f} detik "
              f"(diulang tiap {cfg.suara.jeda_ulang_detik:.0f} detik)")
    print(f"Kalibrasi: {cfg.kalibrasi_detik:.0f} detik setelah wajah terlihat")
    print(f"Mati auto: wajah hilang >{cfg.mati_tanpa_wajah_detik:.0f} detik saat monitoring")
    print(f"Mode     : {'jendela OpenCV' if tampilkan else 'headless (terminal)'}")
    print("Tombol   : spasi mulai | q keluar | c kalibrasi ulang | d debug\n")

    with PembacaTombol() as tombol_terminal:
        # Tanpa terminal interaktif (mis. keluaran dialihkan ke berkas atau
        # dijalankan systemd) tombol SPASI tidak mungkin ditekan, jadi sistem
        # langsung menyala. Sumber berkas video juga tidak perlu ditunggu.
        auto = arg.langsung or dari_berkas or (not tampilkan and not tombol_terminal.aktif)
        return _loop(arg, cfg, detektor, asisten, tombol_terminal,
                     tampilkan, dari_berkas, auto)


def _loop(arg, cfg: Config, detektor: DetektorWajah, asisten: AsistenSuara,
          tombol_terminal: PembacaTombol, tampilkan: bool, dari_berkas: bool,
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

    def tombol_ditekan(frame) -> int:
        """Tampilkan frame (bila perlu) lalu baca satu tombol; -1 = tidak ada."""
        nonlocal jendela_dibuat
        if tampilkan:
            if jendela_dibuat:
                cv2.imshow(JUDUL, frame)
            else:
                # Pembuatan jendela pertama memicu beberapa pesan Qt/X11 yang
                # tidak ada hubungannya dengan program.
                with redam_stderr():
                    cv2.imshow(JUDUL, frame)
                jendela_dibuat = True
            return cv2.waitKey(1) & 0xFF
        return tombol_terminal.baca()

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
        sesi = Sesi(Kalibrator(cfg.kalibrasi_detik))
        keadaan = KALIBRASI
        print(f"\n[sistem] menyala -- {info_kamera(cap)}")
        return True

    def matikan(alasan: str) -> None:
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
        salam_diucapkan = False

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
                    salam_diucapkan = True
                    if not tampilkan:
                        sys.stdout.write("\r  SIAGA -- tekan SPASI untuk memulai sistem"
                                         "        ")
                        sys.stdout.flush()
                tombol = tombol_ditekan(layar_siaga(cfg.kamera.lebar, cfg.kamera.tinggi))
                if tombol in (ord("q"), ESC):
                    break
                if tombol == SPASI:
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

            catatan = ""
            # --- KALIBRASI -----------------------------------------------
            if keadaan == KALIBRASI:
                catatan = _tahap_kalibrasi(cfg, sesi, asisten, hasil, t)
                if sesi.penilai is not None:
                    keadaan = MONITOR
                if tampilkan or perekam is not None:
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
                _catat_episode(sesi, st, t)
                habis, catatan = _tahap_monitor(cfg, sesi, asisten, st, t, dari_berkas)
                if habis:
                    matikan(f"wajah hilang lebih dari "
                            f"{cfg.mati_tanpa_wajah_detik:.0f} detik, sistem dimatikan.")
                    continue
                if tampilkan or perekam is not None:
                    gambar_overlay(frame, hasil, st, fps, debug,
                                   asisten.sedang_bicara, catatan)
                if not tampilkan and t - cetak_terakhir > 0.2:
                    cetak_status(st, fps, catatan)
                    cetak_terakhir = t

            if perekam is not None:
                perekam.write(frame)

            tombol = tombol_ditekan(frame)
            if tombol in (ord("q"), ESC):
                break
            if tombol == ord("c"):
                sesi.kalibrator = Kalibrator(cfg.kalibrasi_detik)
                sesi.penilai = None
                sesi.diumumkan = False
                keadaan = KALIBRASI
                print("\nKalibrasi ulang...")
            if tombol == ord("d"):
                debug = not debug
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


def _catat_episode(sesi: Sesi, st: Status, t: float) -> None:
    """Catat awal & akhir tiap periode KANTUK untuk ringkasan sesi."""
    # Waktu dicatat relatif terhadap awal monitoring supaya terbaca sebagai
    # menit:detik sesi, bukan angka jam monotonic sistem.
    lewat = t - sesi.mulai
    if st.level != sesi.level_lalu:
        if st.level == KANTUK:
            sesi.episode.append({"mulai": lewat, "selesai": lewat,
                                 "alasan": list(st.alasan)})
        sesi.level_lalu = st.level
    elif st.level == KANTUK and sesi.episode:
        sesi.episode[-1]["selesai"] = lewat
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
    if rekam:
        print(f"\nVideo anotasi   : {rekam}")


def _jam(detik: float) -> str:
    return f"{int(detik) // 60:02d}:{detik % 60:05.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
