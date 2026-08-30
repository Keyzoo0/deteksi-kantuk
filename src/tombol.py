"""Pembacaan tombol dari terminal untuk mode headless (tanpa jendela OpenCV).

Saat jendela video ditampilkan, tombol dibaca `cv2.waitKey`. Di mode headless
tidak ada jendela, sehingga tombol SPASI untuk memulai sistem dibaca langsung
dari stdin -- tanpa perlu menekan Enter, dan tanpa menghentikan loop deteksi
(pembacaan selalu tidak memblokir).

Bila stdin bukan terminal (mis. keluaran dialihkan ke berkas, atau dijalankan
lewat systemd), pembacaan dimatikan; pemanggil yang memutuskan apa artinya --
di program ini sistem langsung berjalan tanpa menunggu tombol.
"""

from __future__ import annotations

import contextlib
import os
import select
import sys

try:                                  # hanya ada di Unix; di Windows lewat
    import termios
    import tty
except ImportError:                   # pragma: no cover
    termios = tty = None              # type: ignore[assignment]


class PembacaTombol(contextlib.AbstractContextManager):
    """Baca satu tombol dari stdin tanpa Enter dan tanpa menunggu."""

    def __init__(self) -> None:
        self.aktif = bool(termios) and sys.stdin.isatty()
        self._asli = None

    def __enter__(self) -> "PembacaTombol":
        if self.aktif:
            try:
                self._asli = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
            except (termios.error, OSError):
                self.aktif = False
        return self

    def __exit__(self, *_) -> None:
        if self._asli is not None:
            with contextlib.suppress(termios.error, OSError):
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._asli)
            self._asli = None

    def baca(self) -> int:
        """Kode tombol yang ditekan, atau -1 bila tidak ada."""
        if not self.aktif:
            return -1
        siap, _, _ = select.select([sys.stdin], [], [], 0)
        if not siap:
            return -1
        data = os.read(sys.stdin.fileno(), 1)
        return data[0] if data else -1
