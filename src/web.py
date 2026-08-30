"""Web server lokal untuk memantau alat tanpa monitor.

Alat dipasang di motor tanpa layar dan tanpa keyboard, jadi satu-satunya cara
melihat apa yang sedang terjadi adalah lewat HP di jaringan yang sama.
Halaman ini menampilkan video langsung, grafik EAR & PERCLOS 2 jam terakhir,
dan riwayat kejadian kantuk.

Dua keputusan yang membentuk modul ini:

* **Tanpa dependensi baru.** Hanya `http.server` dari pustaka standar. Untuk
  empat rute, menambah Flask beserta rantai paketnya tidak sepadan -- dan alat
  ini harus tetap bisa dipasang di Raspberry Pi yang sedang tanpa internet.
* **Loop deteksi tetap pemilik tunggal kamera.** Web server tidak pernah
  menyentuh `/dev/video0`; ia hanya membaca frame terakhir yang dititipkan
  loop deteksi. Dua proses berebut kamera pasti gagal.

Frame baru dikodekan ke JPEG hanya ketika ada yang menonton, dan paling cepat
beberapa kali per detik: menyandikan tiap frame padahal tidak ada penonton itu
memakan CPU yang dibutuhkan MediaPipe.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
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

    def __init__(self, cfg: WebConfig) -> None:
        self.cfg = cfg
        self._kunci = threading.Lock()
        self._jpeg: bytes | None = None
        self._jpeg_saat = 0.0
        self._penonton = 0
        self._sampel_saat = 0.0
        # 2 jam @1 Hz = 7200 titik; deque memangkas sendiri yang tertua.
        self.sampel: deque[Cuplikan] = deque(maxlen=int(cfg.jendela_detik))
        self.riwayat: list[dict] = []
        self.status: dict = {"keadaan": "siaga"}

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
                "sampel": [[round(s.detik, 1), round(s.ear, 1),
                            round(s.perclos, 1), s.tingkat] for s in self.sampel],
                "riwayat": self.riwayat[-50:],
            }


HALAMAN = """<!doctype html><html lang="id"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitor Kantuk</title><style>
:root{color-scheme:dark}
body{margin:0;background:#141518;color:#e8e8ea;font:14px system-ui,sans-serif}
header{padding:10px 14px;background:#1d1f24;display:flex;gap:14px;align-items:center;
 flex-wrap:wrap;position:sticky;top:0}
h1{font-size:15px;margin:0;font-weight:600}
.pil{padding:3px 10px;border-radius:99px;font-weight:600;font-size:12px}
.aman{background:#16391f;color:#7ee29a}.kantuk{background:#3d1a1a;color:#ff8a8a}
.mati{background:#2a2c33;color:#9aa}
main{padding:14px;display:grid;gap:14px;max-width:900px;margin:auto}
.kotak{background:#1d1f24;border-radius:10px;padding:12px}
.kotak h2{font-size:12px;margin:0 0 8px;color:#9aa;text-transform:uppercase;
 letter-spacing:.06em}
img{width:100%;border-radius:8px;display:block;background:#000}
canvas{width:100%;height:190px}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:5px 6px;border-bottom:1px solid #2a2c33;text-align:left}
th{color:#9aa;font-weight:500}
.metrik{display:flex;gap:18px;flex-wrap:wrap;font-variant-numeric:tabular-nums}
.metrik div{min-width:88px}.metrik b{display:block;font-size:17px}
.metrik span{color:#9aa;font-size:11px}
a{color:#7fb4ff}
button{border:0;border-radius:7px;color:#e8e8ea;padding:7px 13px;
 font:inherit;cursor:pointer;background:#2f323a}
button:hover{background:#3a3e48}
button.bahaya{background:#4a1f1f;color:#ff9c9c}
.baris{display:flex;justify-content:space-between;align-items:center;gap:10px;
 padding:7px 0;border-bottom:1px solid #2a2c33}
.baris:last-child{border-bottom:0}
.kecil{color:#9aa;font-size:12px}
input{background:#14161a;border:1px solid #333;border-radius:6px;color:#e8e8ea;
 padding:6px 9px;font:inherit;max-width:150px}
</style>
<header><h1>Monitor Kantuk</h1><span id="pil" class="pil mati">memuat…</span>
<span id="alasan" style="color:#9aa"></span></header>
<main>
<div class="kotak"><h2>Kamera</h2><img src="/video" alt="video langsung"></div>
<div class="kotak"><h2>Kondisi sekarang</h2><div class="metrik" id="metrik"></div></div>
<div class="kotak"><h2>EAR &amp; PERCLOS — 2 jam terakhir</h2>
 <canvas id="grafik"></canvas>
 <div style="color:#9aa;font-size:12px;margin-top:6px">
  <span style="color:#7ee29a">■</span> EAR (% baseline)
  <span style="color:#ffc46b;margin-left:12px">■</span> PERCLOS (%)
  <span style="color:#ff8a8a;margin-left:12px">■</span> alarm</div></div>
<div class="kotak"><h2>Riwayat kejadian</h2><table id="riwayat">
 <tr><th>Waktu</th><th>Lama</th><th>Alasan</th><th>Posisi</th></tr></table></div>

<div class="kotak"><h2>Speaker Bluetooth</h2>
 <div id="audio" style="color:#9aa;margin-bottom:8px"></div>
 <button onclick="pindai()">Pindai perangkat</button>
 <div id="bt"></div></div>

<div class="kotak"><h2>WiFi</h2>
 <button onclick="wifi()">Cari jaringan</button>
 <div id="wifi"></div></div>

<div class="kotak"><h2>Sistem</h2>
 <div id="info" class="metrik"></div>
 <div style="margin-top:10px">
  <button onclick="sistem('reboot')">Reboot</button>
  <button class="bahaya" onclick="sistem('matikan')">Matikan Pi</button></div>
 <div id="pesan" style="margin-top:8px;color:#ffc46b"></div></div>
</main>
<script>
const $ = s => document.querySelector(s);
function gambar(sampel){
  const c = $('#grafik'), r = window.devicePixelRatio || 1;
  c.width = c.clientWidth * r; c.height = c.clientHeight * r;
  const g = c.getContext('2d'), W = c.width, H = c.height;
  g.clearRect(0,0,W,H);
  g.strokeStyle = '#2a2c33'; g.lineWidth = 1;
  for (let i = 0; i <= 4; i++){ const y = H*i/4; g.beginPath();
    g.moveTo(0,y); g.lineTo(W,y); g.stroke(); }
  if (!sampel.length){ g.fillStyle='#666'; g.font=`${13*r}px sans-serif`;
    g.fillText('belum ada data', 10*r, H/2); return; }
  const t0 = sampel[0][0], t1 = Math.max(sampel[sampel.length-1][0], t0+60);
  const x = t => (t - t0) / (t1 - t0) * W;
  const y = v => H - Math.min(v,150)/150 * H;
  // penanda alarm digambar lebih dulu supaya garis metrik tetap terbaca
  g.fillStyle = 'rgba(255,138,138,.22)';
  sampel.forEach(s => { if (s[3] > 0) g.fillRect(x(s[0]), 0, Math.max(1,r), H); });
  [[1,'#7ee29a'],[2,'#ffc46b']].forEach(([i,warna]) => {
    g.beginPath(); g.strokeStyle = warna; g.lineWidth = 1.6*r;
    sampel.forEach((s,n) => n ? g.lineTo(x(s[0]), y(s[i])) : g.moveTo(x(s[0]), y(s[i])));
    g.stroke();
  });
}
async function muat(){
  try{
    const d = await (await fetch('/data')).json(), s = d.status;
    const pil = $('#pil');
    pil.textContent = s.level || s.keadaan || '—';
    pil.className = 'pil ' + (s.level === 'KANTUK' ? 'kantuk' : s.level ? 'aman' : 'mati');
    $('#alasan').textContent = s.alasan || '';
    $('#metrik').innerHTML = [
      ['EAR', (s.ear ?? 0).toFixed(0) + '%'], ['PERCLOS', (s.perclos ?? 0).toFixed(0) + '%'],
      ['Kedip', s.kedip ?? 0], ['Menguap', s.menguap ?? 0],
      ['Alarm', 'tingkat ' + (s.tingkat ?? 0)], ['FPS', (s.fps ?? 0).toFixed(1)],
      ['GPS', s.gps || '—'],
    ].map(([k,v]) => `<div><b>${v}</b><span>${k}</span></div>`).join('');
    gambar(d.sampel);
    $('#riwayat').innerHTML = '<tr><th>Waktu</th><th>Lama</th><th>Alasan</th>'
      + '<th>Posisi</th></tr>' + d.riwayat.slice().reverse().map(k =>
      `<tr><td>${k.jam}</td><td>${k.lama}</td><td>${k.alasan}</td><td>` +
      (k.tautan ? `<a href="${k.tautan}" target="_blank">peta</a>` : '—') +
      '</td></tr>').join('');
  }catch(e){ $('#pil').textContent = 'terputus'; }
}
async function aksi(badan){
  $('#pesan').textContent = 'memproses…';
  try{
    const r = await (await fetch('/aksi', {method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify(badan)})).json();
    $('#pesan').textContent = r.pesan || (r.ok ? 'berhasil' : 'gagal');
    return r;
  }catch(e){ $('#pesan').textContent = 'gagal menghubungi alat'; return {}; }
}
async function pindai(){
  $('#bt').innerHTML = '<div class="kecil">memindai 8 detik…</div>';
  const r = await aksi({perintah:'bt_pindai'});
  $('#audio').textContent = 'Keluaran aktif: ' + (r.audio || '—');
  $('#bt').innerHTML = (r.daftar||[]).map(d => `<div class="baris"><div>${d.nama}
    <div class="kecil">${d.mac}${d.terhubung ? ' · tersambung' : d.dikenal ? ' · dikenal' : ''}</div></div>
    <div>${d.terhubung
      ? `<button onclick="btAksi('${d.mac}','putus')">Putuskan</button>`
      : `<button onclick="btAksi('${d.mac}','sambung')">Sambungkan</button>`}</div></div>`
  ).join('') || '<div class="kecil">tidak ada perangkat terdeteksi</div>';
}
async function btAksi(mac, a){ await aksi({perintah:'bt_aksi', mac, aksi:a}); pindai(); }
async function wifi(){
  $('#wifi').innerHTML = '<div class="kecil">mencari…</div>';
  const r = await aksi({perintah:'wifi_daftar'});
  $('#wifi').innerHTML = (r.daftar||[]).map(j => `<div class="baris"><div>${j.ssid}
    <div class="kecil">sinyal ${j.sinyal}%${j.aktif ? ' · tersambung' : ''}${j.aman ? ' · terkunci' : ''}</div></div>
    <div>${j.aktif ? '<span class="kecil">aktif</span>' :
      `<input type="password" placeholder="sandi" id="s-${CSS.escape(j.ssid)}">
       <button onclick="wifiSambung('${j.ssid.replace(/'/g,"\\'")}')">Sambung</button>`}</div></div>`
  ).join('') || '<div class="kecil">tidak ada jaringan terdeteksi</div>';
}
async function wifiSambung(ssid){
  const el = document.getElementById('s-' + ssid);
  await aksi({perintah:'wifi_sambung', ssid, sandi: el ? el.value : ''});
}
async function sistem(a){
  if (!confirm(a === 'matikan' ? 'Matikan Raspberry Pi sekarang?' : 'Reboot sekarang?')) return;
  await aksi({perintah:'sistem', aksi:a});
}
async function muatInfo(){
  const r = await aksi({perintah:'info'});
  $('#pesan').textContent = '';
  $('#info').innerHTML = Object.entries(r.info||{}).map(([k,v]) =>
    `<div><b style="font-size:14px">${v}</b><span>${k}</span></div>`).join('');
  $('#audio').textContent = 'Keluaran aktif: ' + ((r.info||{}).audio || '—');
}
muat(); setInterval(muat, 2000); muatInfo();
</script></html>"""


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
        if jalur == "/":
            self._kirim(HALAMAN.encode(), "text/html; charset=utf-8")
        elif jalur == "/data":
            self._kirim(json.dumps(self.keadaan.data()).encode(), "application/json")
        elif jalur == "/video":
            self._aliran_video()
        else:
            self.send_error(404)

    def do_POST(self) -> None:               # noqa: N802 (nama dari pustaka)
        if self.path.split("?")[0] != "/aksi":
            self.send_error(404)
            return
        try:
            panjang = int(self.headers.get("Content-Length") or 0)
            badan = json.loads(self.rfile.read(panjang) or b"{}")
        except (ValueError, OSError):
            self.send_error(400)
            return
        self._kirim(json.dumps(self._aksi(badan)).encode(), "application/json")

    @staticmethod
    def _aksi(badan: dict) -> dict:
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
