"""Pengiriman notifikasi ke kerabat lewat Telegram.

Dua hal yang menentukan bentuk modul ini:

* **Jaringan tidak boleh menghambat deteksi.** Panggilan HTTP bisa menggantung
  belasan detik, sedangkan loop deteksi harus tetap ~15 FPS. Karena itu
  `kirim()` hanya menitipkan pesan ke antrean, dan sebuah thread pekerja yang
  mengurus pengirimannya.
* **Sinyal di jalan pasti putus-putus.** Pesan yang gagal terkirim disimpan ke
  berkas antrean dan dicoba lagi berkala, jadi laporan tetap sampai begitu
  jaringan kembali -- lengkap dengan jam kejadian aslinya.

Token bot dan daftar chat kerabat dibaca dari `rahasia.json` yang sengaja
tidak ikut repo. Isi berkasnya:

    {"telegram_token": "...", "telegram_chat_id": [123456789]}

Foto sengaja tidak ikut disimpan ke antrean: berkas gambar membuat antrean
membengkak, sedangkan yang paling penting untuk kerabat -- jam, alasan, dan
posisi -- semuanya ada di teks.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import NotifikasiConfig

API = "https://api.telegram.org/bot{token}/{metode}"


@dataclass
class Pesan:
    teks: str
    foto: bytes | None = None
    saat: float = 0.0                 # time.time() saat kejadian, bukan saat kirim


class Notifikasi:
    def __init__(self, cfg: NotifikasiConfig, akar: Path) -> None:
        self.cfg = cfg
        self.akar = akar
        self._token = ""
        self._chat: list[int] = []
        self._antrean: queue.Queue[Pesan] = queue.Queue()
        self._berkas = akar / cfg.berkas_antrean
        self._jalan = False
        self.terkirim = 0
        self.gagal = 0
        self._daring = True              # dianggap ada sampai terbukti tidak
        self._cek_daring = 0.0

        rahasia = akar / cfg.berkas_rahasia
        if not cfg.aktif:
            self.keterangan = "dimatikan"
            return
        try:
            data = json.loads(rahasia.read_text(encoding="utf-8"))
            self._token = str(data.get("telegram_token", "")).strip()
            self._chat = [int(c) for c in data.get("telegram_chat_id", [])]
        except (OSError, ValueError, TypeError) as e:
            self.keterangan = f"{cfg.berkas_rahasia} tidak terbaca ({type(e).__name__})"
            return
        if not self._token:
            self.keterangan = f"token belum diisi di {cfg.berkas_rahasia}"
            return
        if not self._chat:
            self.keterangan = ("token siap, tapi belum ada kerabat terdaftar -- "
                               "jalankan tools/daftar_kerabat.py")
        else:
            self.keterangan = f"Telegram, {len(self._chat)} kerabat terdaftar"
        self._jalan = True
        threading.Thread(target=self._pekerja, daemon=True).start()

    @property
    def siap(self) -> bool:
        return self._jalan and bool(self._chat)

    @property
    def jumlah_kerabat(self) -> int:
        return len(self._chat)

    @property
    def daring(self) -> bool:
        """Apakah Telegram bisa dihubungi?

        Diperiksa di thread pekerja, bukan di loop deteksi, karena pemeriksaan
        jaringan bisa menggantung beberapa detik. Yang diuji sengaja alamat
        Telegram itu sendiri, bukan sembarang situs: yang penting bukan
        "ada internet", melainkan "notifikasi bisa sampai".
        """
        return self._daring

    # --- dipanggil dari loop utama (tidak pernah memblokir) ------------------
    def kirim(self, teks: str, foto: bytes | None = None) -> bool:
        if not self.siap:
            return False
        self._antrean.put(Pesan(teks, foto, time.time()))
        return True

    # --- thread pekerja ------------------------------------------------------
    def _pekerja(self) -> None:
        while self._jalan:
            self._periksa_daring()
            try:
                pesan = self._antrean.get(timeout=self.cfg.jeda_cek_daring_detik)
            except queue.Empty:
                if self._daring:
                    self._coba_tertunda()
                continue
            if not self._kirim_sekarang(pesan):
                self._tunda(pesan)

    def _periksa_daring(self) -> None:
        sekarang = time.monotonic()
        if sekarang - self._cek_daring < self.cfg.jeda_cek_daring_detik:
            return
        self._cek_daring = sekarang
        try:
            with socket.create_connection(("api.telegram.org", 443), timeout=5):
                self._daring = True
        except OSError:
            self._daring = False

    def _kirim_sekarang(self, pesan: Pesan) -> bool:
        berhasil = False
        for chat in self._chat:
            if pesan.foto and self.cfg.kirim_foto:
                ok = self._unggah_foto(chat, pesan.teks, pesan.foto)
            else:
                ok = self._panggil("sendMessage", {
                    "chat_id": chat, "text": pesan.teks,
                    "disable_web_page_preview": "true"})
            berhasil = berhasil or ok
        if berhasil:
            self.terkirim += 1
        else:
            self.gagal += 1
        return berhasil

    def _panggil(self, metode: str, data: dict) -> bool:
        url = API.format(token=self._token, metode=metode)
        badan = urllib.parse.urlencode(data).encode()
        try:
            with urllib.request.urlopen(url, badan, timeout=self.cfg.batas_detik) as r:
                return json.load(r).get("ok", False)
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def _unggah_foto(self, chat: int, teks: str, foto: bytes) -> bool:
        """sendPhoto memakai multipart; dirakit sendiri agar tanpa dependensi."""
        batas = uuid.uuid4().hex
        bagian = []
        for nama, nilai in (("chat_id", str(chat)), ("caption", teks)):
            bagian.append(f'--{batas}\r\nContent-Disposition: form-data; name="{nama}"'
                          f'\r\n\r\n{nilai}\r\n'.encode())
        bagian.append(f'--{batas}\r\nContent-Disposition: form-data; name="photo"; '
                      f'filename="kantuk.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode())
        bagian.append(foto + f"\r\n--{batas}--\r\n".encode())
        badan = b"".join(bagian)
        permintaan = urllib.request.Request(
            API.format(token=self._token, metode="sendPhoto"), badan,
            {"Content-Type": f"multipart/form-data; boundary={batas}"})
        try:
            with urllib.request.urlopen(permintaan, timeout=self.cfg.batas_detik) as r:
                return json.load(r).get("ok", False)
        except (urllib.error.URLError, OSError, ValueError):
            return False

    # --- antrean di disk -----------------------------------------------------
    def _tunda(self, pesan: Pesan) -> None:
        try:
            with self._berkas.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"teks": pesan.teks, "saat": pesan.saat}) + "\n")
        except OSError:
            pass

    def _coba_tertunda(self) -> None:
        """Kirim ulang pesan yang sempat gagal; sisanya ditulis balik."""
        if not self._berkas.exists():
            return
        try:
            baris = self._berkas.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        tersisa = []
        for b in baris:
            try:
                d = json.loads(b)
            except ValueError:
                continue
            umur = max(0, int(time.time() - d.get("saat", time.time())))
            teks = d["teks"] + f"\n\n(tertunda {umur // 60} menit karena sinyal hilang)"
            if not self._kirim_sekarang(Pesan(teks, None, d.get("saat", 0))):
                tersisa.append(b)
        try:
            if tersisa:
                self._berkas.write_text("\n".join(tersisa) + "\n", encoding="utf-8")
            else:
                self._berkas.unlink()
        except OSError:
            pass

    def tutup(self) -> None:
        self._jalan = False
