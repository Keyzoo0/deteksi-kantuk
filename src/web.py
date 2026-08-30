"""Web server lokal untuk memantau alat tanpa monitor.

Alat dipasang di motor tanpa layar dan tanpa keyboard, jadi satu-satunya cara
melihat apa yang sedang terjadi adalah lewat HP di jaringan yang sama.
Halaman ini menampilkan video langsung, grafik EAR & PERCLOS 2 jam terakhir,
dan riwayat kejadian kantuk.

Antarmukanya dibangun dengan **Vite + React + shadcn/ui** di folder `web/`,
lalu hasil `npm run build` (folder `web/dist`) disajikan langsung oleh server
ini. Raspberry Pi tidak perlu Node sama sekali -- yang dikirim ke Pi hanya
berkas statis hasil build, dan berkas itu ikut masuk repo.

Dua keputusan yang membentuk modul ini:

* **Sisi Python tetap tanpa dependensi.** Hanya `http.server` dari pustaka
  standar; ia cuma menyajikan berkas statis dan beberapa rute JSON.
* **Loop deteksi tetap pemilik tunggal kamera.** Web server tidak pernah
  menyentuh `/dev/video0`; ia hanya membaca frame terakhir yang dititipkan
  loop deteksi. Dua proses berebut kamera pasti gagal.

Frame baru dikodekan ke JPEG hanya ketika ada yang menonton, dan paling cepat
beberapa kali per detik: menyandikan tiap frame padahal tidak ada penonton itu
memakan CPU yang dibutuhkan MediaPipe.
"""

from __future__ import annotations

import base64
import binascii
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from . import sistem
from .config import WebConfig


@dataclass
class Cuplikan:
    """Satu titik grafik (disimpan ±1 Hz, bukan tiap frame)."""

    detik: float          # detik sejak sesi dimulai
    ear: float            # persen terhadap baseline
    perclos: float        # persen
    tingkat: int          # tingkat alarm saat itu


class KeadaanBersama:
    """Papan tulis antara loop deteksi dan web server."""

    def __init__(self, cfg: WebConfig, akar: Path | None = None) -> None:
        self.cfg = cfg
        self.akar = akar or Path(__file__).resolve().parent.parent
        self.folder_web = self.akar / cfg.folder_web
        self._kunci = threading.Lock()
        self._jpeg: bytes | None = None
        self._jpeg_saat = 0.0
        self._penonton = 0
        self._sampel_saat = 0.0
        # 2 jam @1 Hz = 7200 titik; deque memangkas sendiri yang tertua.
        self.sampel: deque[Cuplikan] = deque(maxlen=int(cfg.jendela_detik))
        self.riwayat: list[dict] = []
        self.status: dict = {"keadaan": "siaga"}
        # Kondisi perangkat & layanan. Dipisah dari `status` karena tetap
        # berlaku walau sistem belum memonitor -- halaman tidak boleh terlihat
        # kosong hanya karena pengendara belum menahan tombol.
        self.alat: dict = {}

    # --- dipanggil loop deteksi ---------------------------------------------
    def perbarui(self, frame, status: dict, cuplikan: Cuplikan | None,
                 t: float) -> None:
        with self._kunci:
            self.status = status
            if cuplikan is not None and t - self._sampel_saat >= self.cfg.jeda_sampel_detik:
                self._sampel_saat = t
                self.sampel.append(cuplikan)
            perlu = (self._penonton > 0
                     and t - self._jpeg_saat >= 1.0 / max(1, self.cfg.fps_video))
        if perlu and frame is not None:
            ok, buf = cv2.imencode(".jpg", frame,
                                   [cv2.IMWRITE_JPEG_QUALITY, self.cfg.mutu_jpeg])
            if ok:
                with self._kunci:
                    self._jpeg = buf.tobytes()
                    self._jpeg_saat = t

    # --- lembar info dokumen (tab "Info" di web) -----------------------------
    def baca_info(self) -> dict:
        try:
            return json.loads((self.akar / self.cfg.berkas_info).read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def tulis_info(self, info: dict) -> dict:
        if not isinstance(info, dict):
            return {"ok": False, "pesan": "isi tidak sah"}
        try:
            (self.akar / self.cfg.berkas_info).write_text(
                json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as e:
            return {"ok": False, "pesan": f"gagal menyimpan: {e.strerror or e}"}
        return {"ok": True, "pesan": "tersimpan"}

    def berkas_logo(self) -> Path | None:
        """Logo unggahan pengguna kalau ada, kalau tidak logo bawaan repo."""
        for nama in (self.cfg.logo_unggah, self.cfg.logo_bawaan):
            berkas = self.akar / nama
            if berkas.is_file():
                return berkas
        return None

    def tulis_logo(self, data_url: str) -> dict:
        # Gambar dikirim sebagai data URL dari peramban; multipart tidak
        # dipakai supaya sisi Python tetap satu jalur JSON saja.
        potongan = data_url.split(",", 1)
        if len(potongan) != 2 or not potongan[0].startswith("data:image/"):
            return {"ok": False, "pesan": "berkas harus berupa gambar"}
        try:
            isi = base64.b64decode(potongan[1], validate=True)
        except (binascii.Error, ValueError):
            return {"ok": False, "pesan": "gambar tidak terbaca"}
        if len(isi) > 2 * 1024 * 1024:
            return {"ok": False, "pesan": "gambar lebih dari 2 MB"}
        tujuan = self.akar / self.cfg.logo_unggah
        try:
            tujuan.parent.mkdir(parents=True, exist_ok=True)
            tujuan.write_bytes(isi)
        except OSError as e:
            return {"ok": False, "pesan": f"gagal menyimpan: {e.strerror or e}"}
        return {"ok": True, "pesan": "logo diganti"}

    def set_alat(self, alat: dict) -> None:
        with self._kunci:
            self.alat = alat

    def catat_kejadian(self, kejadian: dict) -> None:
        with self._kunci:
            self.riwayat.append(kejadian)
            del self.riwayat[:-200]         # simpan 200 kejadian terakhir saja

    # --- dibaca web server ---------------------------------------------------
    @property
    def ada_penonton(self) -> bool:
        """Ada yang sedang membuka video? Dipakai loop deteksi untuk memutuskan
        apakah overlay perlu digambar -- di mode headless tanpa penonton,
        menggambar anotasi hanya membuang CPU."""
        with self._kunci:
            return self._penonton > 0

    def ambil_jpeg(self) -> bytes | None:
        with self._kunci:
            return self._jpeg

    def tonton(self, tambah: int) -> None:
        with self._kunci:
            self._penonton = max(0, self._penonton + tambah)

    def data(self) -> dict:
        with self._kunci:
            return {
                "status": self.status,
                "alat": self.alat,
                "sampel": [[round(s.detik, 1), round(s.ear, 1),
                            round(s.perclos, 1), s.tingkat] for s in self.sampel],
                "riwayat": self.riwayat[-50:],
            }


TIPE = {".html": "text/html; charset=utf-8", ".js": "text/javascript",
        ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png",
        ".jpg": "image/jpeg", ".woff2": "font/woff2", ".json": "application/json",
        ".ico": "image/x-icon"}

BELUM_DIBANGUN = b"""<!doctype html><meta charset="utf-8">
<body style="font:14px system-ui;padding:2rem;max-width:40rem">
<h1>Antarmuka belum dibangun</h1>
<p>Jalankan di komputer pengembang, lalu salin folder <code>web/dist</code> ke Pi:</p>
<pre>cd web &amp;&amp; npm install &amp;&amp; npm run build</pre>
<p>Rute data tetap berfungsi: <code>/data</code>, <code>/info</code>, <code>/video</code>.</p>
"""


class _Penangan(BaseHTTPRequestHandler):
    keadaan: KeadaanBersama = None            # type: ignore[assignment]
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args) -> None:
        pass                                   # jangan mengotori keluaran program

    def _kirim(self, isi: bytes, tipe: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", tipe)
        self.send_header("Content-Length", str(len(isi)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(isi)

    def do_GET(self) -> None:                  # noqa: N802 (nama dari pustaka)
        jalur = self.path.split("?")[0]
        if jalur == "/data":
            self._kirim(json.dumps(self.keadaan.data()).encode(), "application/json")
        elif jalur == "/info":
            self._kirim(json.dumps(self.keadaan.baca_info()).encode(), "application/json")
        elif jalur == "/logo":
            berkas = self.keadaan.berkas_logo()
            if berkas is None:
                self.send_error(404)
            else:
                self._kirim(berkas.read_bytes(),
                            TIPE.get(berkas.suffix.lower(), "application/octet-stream"))
        elif jalur == "/video":
            self._aliran_video()
        else:
            self._kirim_statis(jalur)

    def _kirim_statis(self, jalur: str) -> None:
        """Sajikan hasil build Vite dari web/dist."""
        akar = self.keadaan.folder_web
        if akar is None or not (akar / "index.html").exists():
            self._kirim(BELUM_DIBANGUN, "text/html; charset=utf-8")
            return
        nama = jalur.lstrip("/") or "index.html"
        berkas = (akar / nama).resolve()
        # Cegah permintaan seperti /../../etc/passwd keluar dari folder build.
        if not str(berkas).startswith(str(akar.resolve())) or not berkas.is_file():
            berkas = akar / "index.html"
        self._kirim(berkas.read_bytes(),
                    TIPE.get(berkas.suffix.lower(), "application/octet-stream"))

    def do_POST(self) -> None:               # noqa: N802 (nama dari pustaka)
        if self.path.split("?")[0] != "/aksi":
            self.send_error(404)
            return
        try:
            panjang = int(self.headers.get("Content-Length") or 0)
            if panjang > 6 * 1024 * 1024:      # logo 2 MB jadi ~2,7 MB base64
                self.send_error(413)
                return
            badan = json.loads(self.rfile.read(panjang) or b"{}")
        except (ValueError, OSError):
            self.send_error(400)
            return
        self._kirim(json.dumps(self._aksi(badan)).encode(), "application/json")

    def _aksi(self, badan: dict) -> dict:
        perintah = badan.get("perintah")
        if perintah == "info":
            return {"ok": True, "info": sistem.info_sistem()}
        if perintah == "bt_pindai":
            return {"ok": True, "daftar": sistem.bluetooth_pindai(),
                    "audio": sistem.audio_sekarang()}
        if perintah == "bt_aksi":
            ok, pesan = sistem.bluetooth_aksi(str(badan.get("mac", "")),
                                              str(badan.get("aksi", "")))
            return {"ok": ok, "pesan": pesan}
        if perintah == "wifi_daftar":
            return {"ok": True, "daftar": sistem.wifi_daftar()}
        if perintah == "wifi_sambung":
            ok, pesan = sistem.wifi_sambung(str(badan.get("ssid", "")),
                                            str(badan.get("sandi", "")))
            return {"ok": ok, "pesan": pesan}
        if perintah == "sistem":
            ok, pesan = sistem.sistem_aksi(str(badan.get("aksi", "")))
            return {"ok": ok, "pesan": pesan or "perintah dikirim"}
        if perintah == "simpan_info":
            return self.keadaan.tulis_info(badan.get("info") or {})
        if perintah == "simpan_logo":
            return self.keadaan.tulis_logo(str(badan.get("data", "")))
        return {"ok": False, "pesan": f"perintah tidak dikenal: {perintah}"}

    def _aliran_video(self) -> None:
        batas = "bingkai"
        self.send_response(200)
        self.send_header("Content-Type",
                         f"multipart/x-mixed-replace; boundary={batas}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.keadaan.tonton(+1)
        try:
            while True:
                jpeg = self.keadaan.ambil_jpeg()
                if jpeg:
                    self.wfile.write(f"--{batas}\r\nContent-Type: image/jpeg\r\n"
                                     f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                    self.wfile.write(jpeg + b"\r\n")
                time.sleep(1.0 / max(1, self.keadaan.cfg.fps_video))
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass                               # penonton menutup halaman: wajar
        finally:
            self.keadaan.tonton(-1)


def mulai_server(keadaan: KeadaanBersama) -> tuple[ThreadingHTTPServer | None, str]:
    """Nyalakan server di thread latar. Kembalikan (server, keterangan)."""
    cfg = keadaan.cfg
    if not cfg.aktif:
        return None, "dimatikan"
    penangan = type("Penangan", (_Penangan,), {"keadaan": keadaan})
    try:
        server = ThreadingHTTPServer((cfg.host, cfg.port), penangan)
    except OSError as e:
        return None, f"gagal ({e.strerror or e})"
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://<alamat-pi>:{cfg.port}"
