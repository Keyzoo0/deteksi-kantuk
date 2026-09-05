"""Peredam pesan bawaan pustaka C (OpenCV/V4L2, MediaPipe, TensorFlow Lite).

Pustaka-pustaka ini menulis langsung ke file descriptor 2, jadi tidak bisa
dibungkam lewat modul `logging` Python. Yang dilakukan di sini: alihkan fd 2
ke berkas sementara selama blok kode berjalan, lalu buang isinya -- kecuali
bila terjadi galat, di mana isinya justru dicetak supaya petunjuknya tidak
hilang.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator


@contextlib.contextmanager
def redam_stderr(tetap_tampilkan_bila_galat: bool = True) -> Iterator[None]:
    sys.stderr.flush()
    asli = os.dup(2)
    tampung = tempfile.TemporaryFile(mode="w+b")
    try:
        os.dup2(tampung.fileno(), 2)
        try:
            yield
        except BaseException:
            os.dup2(asli, 2)                    # kembalikan dulu agar bisa dicetak
            if tetap_tampilkan_bila_galat:
                tampung.seek(0)
                pesan = tampung.read().decode("utf-8", "replace").strip()
                if pesan:
                    print(pesan, file=sys.stderr)
            raise
    finally:
        sys.stderr.flush()
        os.dup2(asli, 2)
        os.close(asli)
        tampung.close()


@contextlib.contextmanager
def redam_pustaka_c() -> Iterator[None]:
    """Buang tulisan pustaka C ke fd 2, tapi pertahankan stderr Python.

    Dipakai selama loop utama: libjpeg mencetak "Corrupt JPEG data ..." tiap
    kali webcam mengirim frame cacat, dan pada webcam yang bermasalah itu
    membanjiri terminal. Traceback serta pesan Python tetap terlihat karena
    `sys.stderr` diarahkan ke salinan fd terminal yang asli.
    """
    sys.stderr.flush()
    asli = os.dup(2)
    kosong = os.open(os.devnull, os.O_WRONLY)
    stderr_lama = sys.stderr
    try:
        os.dup2(kosong, 2)
        sys.stderr = os.fdopen(os.dup(asli), "w", buffering=1)
        yield
    finally:
        try:
            sys.stderr.flush()
            sys.stderr.close()
        except Exception:
            pass
        sys.stderr = stderr_lama
        os.dup2(asli, 2)
        os.close(asli)
        os.close(kosong)


def siapkan_font_qt() -> None:
    """Sediakan font untuk jendela Qt bawaan OpenCV.

    Wheel opencv-python tidak menyertakan font, sehingga setiap kali jendela
    dibuka Qt mencetak "QFontDatabase: Cannot find font directory ...".
    Menyalin satu font sistem ke folder yang dicari Qt membuat peringatan itu
    hilang. Gagal menyalin bukan masalah -- hanya berpengaruh ke pesan log.
    """
    try:
        import shutil
        import cv2

        tujuan = Path(cv2.__file__).parent / "qt" / "fonts"
        if tujuan.exists() and any(tujuan.glob("*.ttf")):
            return
        for kandidat in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ):
            asal = Path(kandidat)
            if asal.exists():
                tujuan.mkdir(parents=True, exist_ok=True)
                shutil.copy2(asal, tujuan / asal.name)
                return
    except Exception:
        pass
