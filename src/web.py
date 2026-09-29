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
import csv
import io
import json
import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from . import sistem
from .config import WebConfig
from .gps import Posisi


@dataclass
class Cuplikan:
    """Satu titik grafik (disimpan ±1 Hz, bukan tiap frame).

    Empat kolom pertama dikirim ke grafik lewat `/data` (ringkas, lihat
    `KeadaanBersama.data`); kolom sisanya cuma dipakai ekspor CSV supaya
    payload `/data` yang dipoll tiap beberapa detik tidak membengkak.
    """

    detik: float           # detik sejak sesi dimulai
    ear: float | None      # persen terhadap baseline; None = wajah tidak terlihat
    perclos: float         # persen
    tingkat: int           # tingkat alarm saat itu
    waktu: float = 0.0     # jam dinding (epoch) saat titik diambil
    sesi_id: str = ""
    wajah: bool = True
    status: str = ""       # AMAN / KANTUK / TANPA_WAJAH
    alasan: str = ""
    ear_raw: float = 0.0
    ear_baseline: float = 0.0
    ear_threshold: float = 0.0
    mata_tertutup: bool = False
    durasi_tertutup: float = 0.0
    mar: float = 0.0
    mar_baseline: float = 0.0
    ambang_mar: float = 0.0
    sedang_menguap: bool = False
    durasi_menguap: float = 0.0
    perclos_siap: bool = False
    kedip_total: int = 0
    menguap_total: int = 0
    fps: float = 0.0
    sampel_kalibrasi: int = 0


def _jam(waktu: float) -> str:
    """Stempel waktu ISO 8601 zona lokal, mis. 2026-09-19T14:03:22.120+07:00."""
    return datetime.fromtimestamp(waktu).astimezone().isoformat(timespec="milliseconds")


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
        # Log kejadian mata/mulut (kedip, terpejam, menguap) untuk CSV
        # tersendiri. Kedipan ±15-20 per menit -> 2 jam kira-kira 2.400
        # baris; batas ini hanya pengaman kalau alat jalan berhari-hari.
        self.peristiwa: deque[dict] = deque(maxlen=20000)
        # Jejak perjalanan untuk peta: (monotonic, lat, lon). Waktu monotonic,
        # bukan jam dinding, karena jam Pi bisa melompat saat NTP tersinkron
        # sesudah boot dan itu akan membuang atau menahan titik secara keliru.
        self.jejak: deque[tuple[float, float, float]] = deque()
        # Log tombol fisik: satu entri per tekanan yang sudah dilepas. Disimpan
        # sebagai momen tekan & lepas, bukan sampel per detik -- ketukan lebih
        # singkat dari 1 detik dan akan lolos dari sampel 1 Hz. Dipangkas
        # memakai waktu monotonic (lihat jejak), ditampilkan memakai jam dinding.
        self.tombol_log: deque[dict] = deque(maxlen=5000)
        self.tombol_langsung: dict = {"ada": False, "ditekan": False, "lama": 0.0,
                                      "ambang": 3.0, "ambang_nyala": 3.0,
                                      "ambang_mati": 8.0, "keadaan": "siaga"}
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

    def catat_posisi(self, posisi: Posisi, ambang_kmh: float) -> None:
        """Tambahkan titik ke jejak peta.

        Hanya dicatat selagi kendaraan melaju dan sudah bergeser cukup jauh:
        posisi GPS saat parkir tetap bergoyang belasan meter, dan mencatat
        goyangan itu menggambar coretan kusut di sekitar tempat parkir
        sekaligus membengkakkan muatan /data yang diambil tiap 2 detik.
        """
        if not posisi.valid or posisi.kecepatan_kmh < ambang_kmh:
            return
        t = time.monotonic()
        with self._kunci:
            if self.jejak:
                _, lat, lon = self.jejak[-1]
                if _jarak_meter(lat, lon, posisi.lat, posisi.lon) < self.cfg.jejak_min_meter:
                    return
            self.jejak.append((t, posisi.lat, posisi.lon))
            self._pangkas_jejak(t)

    def _pangkas_jejak(self, t: float) -> None:
        while self.jejak and t - self.jejak[0][0] > self.cfg.jendela_detik:
            self.jejak.popleft()

    def bersihkan(self) -> None:
        """Buang seluruh data sesi: grafik, riwayat, jejak, dan log kejadian.

        Dipakai saat pengendara mematikan sistem lewat tombol: menyalakannya
        lagi berarti perjalanan baru, dan grafik yang masih memuat sisa
        perjalanan sebelumnya membuat sumbu waktunya melompat-lompat.

        Log tombol sengaja TIDAK ikut dikosongkan: ia mencatat alat, bukan
        perjalanan -- dan tekanan "mematikan" yang memicu penghapusan ini
        justru harus tetap terlihat di log.
        """
        with self._kunci:
            self.sampel.clear()
            self.riwayat.clear()
            self.jejak.clear()
            self.peristiwa.clear()
            self._sampel_saat = 0.0
            self.status = {"keadaan": "siaga"}

    def set_tombol(self, ada: bool, ditekan: bool, lama: float, ambang_nyala: float,
                   ambang_mati: float, keadaan: str) -> None:
        """Keadaan tombol saat ini, diperbarui loop tiap putaran."""
        with self._kunci:
            self.tombol_langsung = {
                "ada": ada, "ditekan": ditekan, "lama": round(lama, 2),
                "ambang": ambang_nyala if keadaan == "siaga" else ambang_mati,
                "ambang_nyala": ambang_nyala, "ambang_mati": ambang_mati,
                "keadaan": keadaan}

    def catat_tombol(self, lama: float, aksi: str, keadaan: str) -> None:
        """Satu tekanan yang baru dilepas, beserta aksi yang dihasilkannya."""
        mono, dinding = time.monotonic(), time.time()
        with self._kunci:
            self.tombol_log.append({"mono": mono, "waktu": dinding, "lama": lama,
                                    "aksi": aksi, "keadaan": keadaan})
            self._pangkas_tombol(mono)

    def _pangkas_tombol(self, t: float) -> None:
        while self.tombol_log and t - self.tombol_log[0]["mono"] > self.cfg.jendela_detik:
            self.tombol_log.popleft()

    def tombol(self) -> dict:
        """Rute /tombol: hanya keadaan langsung, supaya ringan diambil 4x/detik.

        Jam alat ikut dikirim: grafik tombol digambar menurut jam alat, bukan
        jam HP yang membuka halaman -- keduanya bisa saja berselisih.
        """
        with self._kunci:
            return {**self.tombol_langsung, "sekarang": round(time.time(), 3)}

    def catat_peristiwa(self, daftar: list[dict]) -> None:
        if daftar:
            with self._kunci:
                self.peristiwa.extend(daftar)

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
            # Dipangkas juga saat dibaca: kendaraan yang parkir lama tidak
            # menambah titik, jadi pemangkasan saat mencatat saja tidak cukup
            # untuk membuang jalur yang sudah lewat 2 jam.
            self._pangkas_jejak(time.monotonic())
            self._pangkas_tombol(time.monotonic())
            return {
                "status": self.status,
                "alat": self.alat,
                # EAR null saat wajah tidak terlihat: grafik memutus garisnya,
                # bukan menggambar 100% palsu (nilai bawaan tanpa pengukuran).
                "sampel": [[round(s.detik, 1),
                            None if s.ear is None else round(s.ear, 1),
                            round(s.perclos, 1), s.tingkat] for s in self.sampel],
                "riwayat": self.riwayat[-50:],
                "jejak": [[round(lat, 6), round(lon, 6)] for _, lat, lon in self.jejak],
                # Jam server ikut dikirim: grafik tombol menggambar relatif
                # terhadap jam alat, bukan jam HP yang bisa saja meleset.
                "tombol": {"sekarang": round(time.time(), 3),
                           "log": [[round(e["waktu"], 3), round(e["lama"], 3),
                                    e["aksi"], e["keadaan"]] for e in self.tombol_log]},
            }

    KOLOM_CSV = ("timestamp", "session_id", "detik", "wajah_terdeteksi", "status",
                 "alasan", "tingkat_alarm", "ear_raw", "ear_persen", "ear_baseline",
                 "ear_threshold", "mata", "durasi_terpejam", "mar_raw", "mar_baseline",
                 "ambang_mar", "mulut", "durasi_menguap", "perclos_persen",
                 "perclos_siap", "kedip_total", "menguap_total", "fps",
                 "sampel_kalibrasi")

    def ekspor_csv(self) -> str:
        """Riwayat grafik 2 jam terakhir sebagai teks CSV (semua kolom).

        Saat wajah tidak terlihat, kolom ukuran mata/mulut dikosongkan:
        angkanya hanya sisa nilai bawaan, bukan hasil pengukuran.
        """
        with self._kunci:
            sampel = list(self.sampel)
        keluaran = io.StringIO()
        # Pemisah baris "\n": modul csv bawaannya "\r\n".
        tulis = csv.writer(keluaran, lineterminator="\n")
        tulis.writerow(self.KOLOM_CSV)
        for s in sampel:
            ukur = (lambda teks: teks) if s.wajah else (lambda _teks: "")
            tulis.writerow((
                _jam(s.waktu) if s.waktu else "", s.sesi_id, f"{s.detik:.1f}",
                int(s.wajah), s.status, s.alasan, s.tingkat,
                ukur(f"{s.ear_raw:.3f}"),
                "" if s.ear is None else f"{s.ear:.1f}",
                f"{s.ear_baseline:.3f}", f"{s.ear_threshold:.3f}",
                ukur("tertutup" if s.mata_tertutup else "terbuka"),
                ukur(f"{s.durasi_tertutup:.1f}"),
                ukur(f"{s.mar:.3f}"),
                f"{s.mar_baseline:.3f}", f"{s.ambang_mar:.3f}",
                ukur("menguap" if s.sedang_menguap else "normal"),
                ukur(f"{s.durasi_menguap:.1f}"),
                f"{s.perclos:.1f}", int(s.perclos_siap),
                s.kedip_total, s.menguap_total, f"{s.fps:.1f}", s.sampel_kalibrasi,
            ))
        return keluaran.getvalue()

    KOLOM_PERISTIWA = ("timestamp_mulai", "timestamp_selesai", "session_id",
                       "jenis", "detik_mulai", "durasi_detik", "catatan")

    def ekspor_peristiwa_csv(self) -> str:
        """Log kejadian kedip / mata terpejam / menguap, satu baris per kejadian."""
        with self._kunci:
            daftar = list(self.peristiwa)
        keluaran = io.StringIO()
        tulis = csv.writer(keluaran, lineterminator="\n")
        tulis.writerow(self.KOLOM_PERISTIWA)
        for p in daftar:
            tulis.writerow((
                _jam(p["waktu"]), _jam(p["waktu"] + p["durasi"]), p["sesi_id"],
                p["jenis"], f"{p['detik']:.2f}", f"{p['durasi']:.3f}", p["catatan"],
            ))
        return keluaran.getvalue()

    KOLOM_TOMBOL = ("timestamp_tekan", "timestamp_lepas", "durasi_detik", "aksi",
                    "keadaan_sistem")

    def ekspor_tombol_csv(self) -> str:
        """Log tombol 2 jam terakhir, satu baris per tekanan."""
        with self._kunci:
            self._pangkas_tombol(time.monotonic())
            daftar = list(self.tombol_log)
        keluaran = io.StringIO()
        tulis = csv.writer(keluaran, lineterminator="\n")
        tulis.writerow(self.KOLOM_TOMBOL)
        for e in daftar:
            tulis.writerow((_jam(e["waktu"] - e["lama"]), _jam(e["waktu"]),
                            f"{e['lama']:.3f}", e["aksi"], e["keadaan"]))
        return keluaran.getvalue()


def _jarak_meter(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Pendekatan equirectangular: untuk jarak belasan meter selisihnya dengan
    # haversine jauh di bawah ketelitian GPS itu sendiri.
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return math.hypot(x, y) * 6_371_000


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

    def _kirim_csv(self, isi_csv: str, nama: str) -> None:
        isi = isi_csv.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Length", str(len(isi)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition",
                         f'attachment; filename="{nama}"')
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
        elif jalur == "/ekspor.csv":
            self._kirim_csv(self.keadaan.ekspor_csv(), "deteksi-kantuk.csv")
        elif jalur == "/ekspor-kejadian.csv":
            self._kirim_csv(self.keadaan.ekspor_peristiwa_csv(),
                            "deteksi-kantuk-kejadian.csv")
        elif jalur == "/ekspor-tombol.csv":
            self._kirim_csv(self.keadaan.ekspor_tombol_csv(), "deteksi-kantuk-tombol.csv")
        elif jalur == "/tombol":
            self._kirim(json.dumps(self.keadaan.tombol()).encode(), "application/json")
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
