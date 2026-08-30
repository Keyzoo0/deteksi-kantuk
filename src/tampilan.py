"""Penggambaran overlay pada frame: status, metrik, dan kontur wajah."""

from __future__ import annotations

import cv2
import numpy as np

from .deteksi import HasilDeteksi, KONTUR_MATA_KANAN, KONTUR_MATA_KIRI, KONTUR_MULUT
from .metrik import KANTUK, Status

FONT = cv2.FONT_HERSHEY_SIMPLEX
HIJAU = (80, 220, 100)
MERAH = (60, 60, 235)
KUNING = (60, 200, 250)
PUTIH = (245, 245, 245)
ABU = (150, 150, 150)
GELAP = (35, 35, 35)


def _panel(frame: np.ndarray, x: int, y: int, w: int, h: int, alpha: float = 0.55) -> None:
    """Kotak gelap semi transparan agar teks tetap terbaca di latar apa pun."""
    x2, y2 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x2 <= x or y2 <= y:
        return
    potongan = frame[y:y2, x:x2]
    frame[y:y2, x:x2] = cv2.addWeighted(potongan, 1 - alpha,
                                        np.full_like(potongan, GELAP), alpha, 0)


def _teks(frame: np.ndarray, teks: str, xy: tuple[int, int], skala: float = 0.5,
          warna: tuple[int, int, int] = PUTIH, tebal: int = 1) -> None:
    cv2.putText(frame, teks, xy, FONT, skala, warna, tebal, cv2.LINE_AA)


def _kontur(frame: np.ndarray, titik: np.ndarray, idx: tuple[int, ...],
            warna: tuple[int, int, int]) -> None:
    pts = titik[list(idx)].astype(np.int32).reshape(-1, 1, 2)
    cv2.polylines(frame, [pts], isClosed=True, color=warna, thickness=2, lineType=cv2.LINE_AA)


def _bar(frame: np.ndarray, x: int, y: int, w: int, h: int, nilai: float,
         ambang: float, warna: tuple[int, int, int]) -> None:
    """Bar horizontal 0..1.5 dengan penanda garis ambang."""
    cv2.rectangle(frame, (x, y), (x + w, y + h), ABU, 1)
    isi = int(w * max(0.0, min(1.0, nilai / 1.5)))
    if isi > 1:
        cv2.rectangle(frame, (x + 1, y + 1), (x + isi, y + h - 1), warna, -1)
    gx = x + int(w * (ambang / 1.5))
    cv2.line(frame, (gx, y - 2), (gx, y + h + 2), KUNING, 1)


def layar_siaga(lebar: int, tinggi: int, pesan: str = "Tahan tombol 3 detik untuk memulai",
                catatan: str = "") -> np.ndarray:
    """Layar tunggu sebelum sistem dinyalakan (kamera sengaja belum dibuka)."""
    frame = np.full((tinggi, lebar, 3), 22, dtype=np.uint8)
    judul = "ASISTEN MONITORING KANTUK"
    (tw, _), _ = cv2.getTextSize(judul, FONT, 0.8, 2)
    _teks(frame, judul, ((lebar - tw) // 2, tinggi // 2 - 40), 0.8, HIJAU, 2)
    (tw, _), _ = cv2.getTextSize(pesan, FONT, 0.6, 2)
    _teks(frame, pesan, ((lebar - tw) // 2, tinggi // 2 + 10), 0.6, PUTIH, 2)
    if catatan:                      # hanya terpakai saat dijalankan berjendela
        (tw, _), _ = cv2.getTextSize(catatan, FONT, 0.45, 1)
        _teks(frame, catatan, ((lebar - tw) // 2, tinggi // 2 + 45), 0.45, ABU)
    cv2.rectangle(frame, (2, 2), (lebar - 3, tinggi - 3), (60, 60, 60), 2)
    return frame


def gambar_kalibrasi(frame: np.ndarray, hasil: HasilDeteksi, sisa: float) -> None:
    """Layar kalibrasi: minta pengguna menatap kamera dengan wajar."""
    tinggi, lebar = frame.shape[:2]
    if hasil.ada_wajah and hasil.titik is not None:
        _kontur(frame, hasil.titik, KONTUR_MATA_KIRI, KUNING)
        _kontur(frame, hasil.titik, KONTUR_MATA_KANAN, KUNING)
        _kontur(frame, hasil.titik, KONTUR_MULUT, KUNING)

    _panel(frame, 0, tinggi // 2 - 60, lebar, 120, alpha=0.65)
    if hasil.ada_wajah:
        judul = f"KALIBRASI {sisa:.1f} detik"
        pesan = "Tatap kamera, mata terbuka wajar, mulut tertutup"
    else:
        judul = "MENUNGGU WAJAH"
        pesan = "Posisikan wajah di depan kamera"
    (tw, _), _ = cv2.getTextSize(judul, FONT, 0.9, 2)
    _teks(frame, judul, ((lebar - tw) // 2, tinggi // 2 - 10), 0.9, KUNING, 2)
    (tw, _), _ = cv2.getTextSize(pesan, FONT, 0.5, 1)
    _teks(frame, pesan, ((lebar - tw) // 2, tinggi // 2 + 25), 0.5, PUTIH, 1)


def gambar_overlay(frame: np.ndarray, hasil: HasilDeteksi, st: Status,
                   fps: float, debug: bool = False,
                   bersuara: bool = False, catatan: str = "") -> None:
    tinggi, lebar = frame.shape[:2]
    kantuk = st.level == KANTUK
    warna_status = MERAH if kantuk else HIJAU

    # --- wajah, mata, mulut ---
    if hasil.ada_wajah and hasil.titik is not None:
        if debug:
            for x, y in hasil.titik.astype(np.int32):
                cv2.circle(frame, (int(x), int(y)), 1, (90, 90, 90), -1)
        warna_mata = MERAH if st.mata_tertutup else HIJAU
        warna_mulut = KUNING if st.sedang_menguap else HIJAU
        _kontur(frame, hasil.titik, KONTUR_MATA_KIRI, warna_mata)
        _kontur(frame, hasil.titik, KONTUR_MATA_KANAN, warna_mata)
        _kontur(frame, hasil.titik, KONTUR_MULUT, warna_mulut)
        if hasil.kotak_wajah:
            x, y, w, h = hasil.kotak_wajah
            cv2.rectangle(frame, (x, y), (x + w, y + h), warna_status, 2)

    # --- panel metrik kiri atas ---
    _panel(frame, 8, 8, 236, 140)
    baris = [
        (f"EAR   {st.ear_norm * 100:5.0f}% baseline",
         MERAH if st.mata_tertutup else PUTIH),
        (f"MAR   {st.mar:5.2f}  (menguap >{st.ambang_mar:.2f})",
         KUNING if st.sedang_menguap else PUTIH),
        (f"PERCLOS {st.perclos * 100:4.0f}%" + ("" if st.perclos_matang else "  (belum matang)"),
         PUTIH if st.perclos_matang else ABU),
        (f"Kedip   {st.kedip_total:3d}  ({st.kedip_per_menit}/menit)", PUTIH),
        (f"Menguap {st.menguap_total:3d}  ({st.menguap_per_menit}/menit)", PUTIH),
    ]
    for i, (t, warna) in enumerate(baris):
        _teks(frame, t, (18, 32 + i * 20), 0.46, warna)
    _bar(frame, 18, 122, 210, 8, st.ear_norm, 0.62, MERAH if st.mata_tertutup else HIJAU)

    # --- banner status bawah ---
    _panel(frame, 0, tinggi - 74, lebar, 74, alpha=0.6)
    label = st.level
    (tw, _), _ = cv2.getTextSize(label, FONT, 1.3, 3)
    _teks(frame, label, ((lebar - tw) // 2, tinggi - 32), 1.3, warna_status, 3)

    detail = ", ".join(st.alasan) if st.alasan else (
        "kondisi normal" if st.ada_wajah else "wajah tidak terdeteksi")
    (tw, _), _ = cv2.getTextSize(detail, FONT, 0.45, 1)
    _teks(frame, detail, ((lebar - tw) // 2, tinggi - 10), 0.45,
          warna_status if st.alasan else ABU)

    if kantuk:   # bingkai merah supaya kentara walau dilihat sekilas
        cv2.rectangle(frame, (2, 2), (lebar - 3, tinggi - 3), MERAH, 4)

    # --- info pojok kanan atas ---
    _teks(frame, f"{fps:4.1f} FPS", (lebar - 88, 26), 0.5, PUTIH)
    if bersuara:      # peringatan lisan sedang berbunyi di speaker
        _teks(frame, "((  SUARA  ))", (lebar - 118, 48), 0.5, KUNING, 2)
    if catatan:       # mis. hitung mundur sebelum sistem mati sendiri
        (tw, _), _ = cv2.getTextSize(catatan, FONT, 0.5, 2)
        _teks(frame, catatan, (lebar - tw - 12, 70), 0.5, MERAH, 2)
