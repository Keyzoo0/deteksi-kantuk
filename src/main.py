"""Program utama deteksi rasa kantuk (mata + mulut) berbasis webcam.

Alur:
    1. Buka webcam.
    2. Kalibrasi beberapa detik -> dapat baseline EAR & MAR pengguna.
    3. Loop: ukur mata/mulut tiap frame, nilai kantuk, tampilkan AMAN/KANTUK.

Jalankan:  python -m src.main            (dari folder project)
Tombol  :  q keluar | c kalibrasi ulang | d tampilkan landmark
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

from .config import Config
from .deteksi import DetektorWajah
from .kamera import buka_kamera, info_kamera, sambung_ulang
from .metrik import KANTUK, Kalibrator, PenilaiKantuk, Status
from .senyap import redam_pustaka_c, redam_stderr, siapkan_font_qt
from .tampilan import gambar_kalibrasi, gambar_overlay

AKAR = Path(__file__).resolve().parent.parent


def argumen() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="deteksi-kantuk",
        description="Deteksi rasa kantuk dari mata (EAR/PERCLOS) dan mulut (menguap).",
    )
    p.add_argument("--config", default=str(AKAR / "config.json"),
                   help="berkas konfigurasi JSON (default: config.json)")
    p.add_argument("--sumber", help="index webcam (0/1) atau path file video")
    p.add_argument("--kalibrasi", type=float, help="durasi kalibrasi dalam detik")
    p.add_argument("--tanpa-jendela", action="store_true",
                   help="mode headless: status dicetak ke terminal, tanpa imshow")
    p.add_argument("--debug", action="store_true", help="gambar seluruh 478 landmark")
    p.add_argument("--rekam", metavar="BERKAS",
                   help="simpan video hasil anotasi (mis. hasil/anotasi.mp4)")
    p.add_argument("--verbose", action="store_true",
                   help="tampilkan pesan bawaan OpenCV/MediaPipe (mis. Corrupt JPEG)")
    return p.parse_args()


def cetak_status(st: Status, fps: float) -> None:
    """Baris status untuk mode headless (menimpa baris yang sama)."""
    tanda = "!!" if st.level == KANTUK else "  "
    alasan = ", ".join(st.alasan) or ("-" if st.ada_wajah else "wajah hilang")
    sys.stdout.write(
        f"\r{tanda} {st.level:<6} | EAR {st.ear_norm * 100:3.0f}% | "
        f"MAR {st.mar:4.2f}/{st.ambang_mar:.2f} | PERCLOS {st.perclos * 100:3.0f}%{'' if st.perclos_matang else '?'} | "
        f"kedip {st.kedip_total:3d} | menguap {st.menguap_total:2d} | "
        f"{fps:4.1f} fps | {alasan:<40}"
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
    if arg.kalibrasi:
        cfg.kalibrasi_detik = arg.kalibrasi
    tampilkan = cfg.tampilkan_jendela and not arg.tanpa_jendela
    # Sumber berupa berkas video diperlakukan berbeda dari webcam: waktunya
    # diambil dari timeline video, bukan jam dinding, supaya durasi kalibrasi
    # dan jendela PERCLOS tetap benar walau pemrosesan lebih cepat/lambat
    # daripada waktu nyata. Efek cermin juga tidak dipakai.
    dari_berkas = not str(cfg.kamera.sumber).isdigit()
    if dari_berkas:
        cfg.kamera.flip_horizontal = False

    print("=" * 62)
    print(" DETEKSI RASA KANTUK - MediaPipe FaceLandmarker + EAR/PERCLOS/MAR")
    print("=" * 62)

    if tampilkan:
        siapkan_font_qt()
    # Kamera dibuka lebih dulu: bila perangkatnya tidak ada, program berhenti
    # sebelum sempat memuat model, sehingga tidak meninggalkan objek MediaPipe
    # yang belum ditutup (pembersihannya saat interpreter mati menghasilkan
    # traceback "Exception ignored in ... FaceLandmarker.__del__").
    cap = buka_kamera(cfg.kamera)
    detektor = DetektorWajah()
    print(f"Kamera   : sumber {cfg.kamera.sumber} -> {info_kamera(cap)}")
    print(f"Kalibrasi: {cfg.kalibrasi_detik:.0f} detik (tatap kamera, mata terbuka wajar)")
    print(f"Mode     : {'jendela OpenCV' if tampilkan else 'headless (terminal)'}")
    print("Tombol   : q keluar | c kalibrasi ulang | d debug landmark\n")

    kalibrator = Kalibrator(cfg.kalibrasi_detik)
    penilai: PenilaiKantuk | None = None
    debug = arg.debug
    fps = 0.0
    t_lalu = time.monotonic()
    cetak_terakhir = 0.0
    gagal_baca = 0
    jendela_dibuat = False
    nomor_frame = 0
    fps_berkas = cap.get(cv2.CAP_PROP_FPS) or 25.0
    perekam: cv2.VideoWriter | None = None
    episode: list[dict] = []      # riwayat periode KANTUK
    level_lalu = None
    kode = 0

    if arg.rekam:
        Path(arg.rekam).parent.mkdir(parents=True, exist_ok=True)
        # Codec mengikuti ekstensi. .webm (VP8) bisa langsung diputar peramban
        # tanpa memasang codec apa pun; .mp4 di sini memakai MPEG-4 Part 2
        # karena wheel OpenCV tidak membawa encoder H.264.
        kode = {"webm": "VP80", "avi": "XVID"}.get(
            Path(arg.rekam).suffix.lstrip(".").lower(), "mp4v")
        perekam = cv2.VideoWriter(
            arg.rekam, cv2.VideoWriter_fourcc(*kode), fps_berkas,
            (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))
        if not perekam.isOpened():
            raise RuntimeError(f"Tidak bisa membuat berkas rekaman '{arg.rekam}' (codec {kode}).")
        print(f"Rekam    : {arg.rekam} (codec {kode})")

    try:
        while True:
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
                        print("Kamera tidak kembali. Program dihentikan.\n"
                              "  Kamera internal yang sering lepas biasanya kena USB "
                              "autosuspend; lihat bagian 'Kalau hasilnya tidak bagus' "
                              "di README.")
                        kode = 1
                        break
                    gagal_baca = 0
                time.sleep(0.03)
                continue
            gagal_baca = 0

            if cfg.kamera.flip_horizontal:
                frame = cv2.flip(frame, 1)

            nomor_frame += 1
            if dari_berkas:
                posisi = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                # Sebagian berkas tidak melaporkan posisi; pakai nomor frame.
                t = posisi if posisi > 0 else nomor_frame / max(1.0, fps_berkas)
            else:
                t = time.monotonic()
            hasil = detektor.proses(frame, int(t * 1000))

            dt = t - t_lalu
            t_lalu = t
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt

            if penilai is None:
                kalibrator.tambah(hasil, t)
                if kalibrator.selesai(t):
                    baseline = kalibrator.hasil()
                    penilai = PenilaiKantuk(cfg.ambang, baseline)
                    print(f"Baseline : EAR {baseline.ear:.3f} | MAR {baseline.mar:.3f} "
                          f"({baseline.sampel} frame)\n")
                else:
                    if tampilkan or perekam is not None:
                        gambar_kalibrasi(frame, hasil, kalibrator.sisa_detik(t))
                    if perekam is not None:
                        perekam.write(frame)
                    if not tampilkan and t - cetak_terakhir > 0.5:
                        sisa = kalibrator.sisa_detik(t)
                        pesan = (f"kalibrasi {sisa:.1f} detik lagi" if hasil.ada_wajah
                                 else "menunggu wajah terdeteksi")
                        sys.stdout.write(f"\r  {pesan:<44}")
                        sys.stdout.flush()
                        cetak_terakhir = t
            else:
                st = penilai.perbarui(hasil, t)

                # Catat awal & akhir tiap periode KANTUK untuk ringkasan.
                if st.level != level_lalu:
                    if st.level == KANTUK:
                        episode.append({"mulai": t, "selesai": t,
                                        "alasan": list(st.alasan)})
                    level_lalu = st.level
                elif st.level == KANTUK and episode:
                    episode[-1]["selesai"] = t
                    for a in st.alasan:
                        pokok = a.split(" ")[0]
                        if not any(x.startswith(pokok) for x in episode[-1]["alasan"]):
                            episode[-1]["alasan"].append(a)

                if tampilkan or perekam is not None:
                    gambar_overlay(frame, hasil, st, fps, debug)
                if perekam is not None:
                    perekam.write(frame)
                if not tampilkan and t - cetak_terakhir > 0.2:
                    cetak_status(st, fps)
                    cetak_terakhir = t

            if tampilkan:
                if jendela_dibuat:
                    cv2.imshow("Deteksi Rasa Kantuk", frame)
                else:
                    # Pembuatan jendela pertama memicu beberapa pesan Qt/X11
                    # yang tidak ada hubungannya dengan program.
                    with redam_stderr():
                        cv2.imshow("Deteksi Rasa Kantuk", frame)
                    jendela_dibuat = True
                tombol = cv2.waitKey(1) & 0xFF
                if tombol in (ord("q"), 27):
                    break
                if tombol == ord("c"):
                    kalibrator = Kalibrator(cfg.kalibrasi_detik)
                    penilai = None
                    print("Kalibrasi ulang...")
                if tombol == ord("d"):
                    debug = not debug
    except KeyboardInterrupt:
        print("\nDihentikan pengguna.")
    finally:
        cap.release()
        detektor.tutup()
        if perekam is not None:
            perekam.release()
        if tampilkan:
            cv2.destroyAllWindows()
        if penilai is not None:
            _cetak_ringkasan(penilai, episode, nomor_frame, t_lalu, arg.rekam)
    return kode


def _cetak_ringkasan(penilai: PenilaiKantuk, episode: list[dict], frame: int,
                     t_akhir: float, rekam: str | None) -> None:
    print("\n" + "=" * 62)
    print(" RINGKASAN SESI")
    print("=" * 62)
    print(f"Frame diproses  : {frame}")
    print(f"Kedipan         : {penilai.kedip_total}")
    print(f"Menguap         : {penilai.menguap_total}")
    print(f"Periode KANTUK  : {len(episode)}")

    for i, e in enumerate(episode, 1):
        lama = e["selesai"] - e["mulai"]
        print(f"  {i}. {_jam(e['mulai'])} - {_jam(e['selesai'])} "
              f"({lama:.1f} detik) : {', '.join(e['alasan'])}")
    if rekam:
        print(f"\nVideo anotasi   : {rekam}")


def _jam(detik: float) -> str:
    return f"{int(detik) // 60:02d}:{detik % 60:05.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
