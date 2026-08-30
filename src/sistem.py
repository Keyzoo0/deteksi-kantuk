"""Pengendalian Raspberry Pi dari web UI: Bluetooth, WiFi, dan daya.

Alat dipasang di motor tanpa monitor dan tanpa keyboard, jadi hal-hal yang
biasanya dikerjakan lewat terminal -- memasangkan speaker Bluetooth baru,
mengganti WiFi saat pindah tempat, mematikan Pi dengan aman -- harus bisa
dilakukan dari HP.

Semuanya dikerjakan dengan memanggil perkakas bawaan sistem (`bluetoothctl`,
`nmcli`, `wpctl`) alih-alih memakai pustaka D-Bus: perintahnya sudah teruji di
Raspberry Pi OS, tidak menambah dependensi, dan hasilnya mudah dibaca manusia
saat ada yang perlu diperiksa lewat SSH.

Perintah yang mengubah keadaan sistem dijalankan lewat `sudo -n` dan hanya
berhasil bila aturan sudoers dari `setup_raspi.sh` sudah terpasang.
"""

from __future__ import annotations

import re
import shutil
import subprocess

BATAS = 20.0            # tidak ada perintah di sini yang wajar berjalan lebih lama


def _jalankan(perintah: list[str], batas: float = BATAS) -> tuple[bool, str]:
    jalur = shutil.which(perintah[0])
    if not jalur:
        return False, f"{perintah[0]} tidak ada di sistem ini"
    try:
        hasil = subprocess.run([jalur, *perintah[1:]], capture_output=True,
                               timeout=batas)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"{type(e).__name__}: {e}"
    keluar = (hasil.stdout + hasil.stderr).decode("utf-8", "replace").strip()
    return hasil.returncode == 0, keluar


# --- Bluetooth ---------------------------------------------------------------
def bluetooth_pindai(detik: int = 8) -> list[dict]:
    """Perangkat Bluetooth di sekitar, plus yang sudah dikenal."""
    _jalankan(["bluetoothctl", "--timeout", str(detik), "scan", "on"], detik + 5)
    perangkat: dict[str, dict] = {}
    for daftar, dikenal in (("devices", False), ("devices", True)):
        ok, keluar = _jalankan(["bluetoothctl", daftar] + (["Paired"] if dikenal else []))
        if not ok:
            continue
        for baris in keluar.splitlines():
            cocok = re.match(r"Device ([0-9A-F:]{17}) (.+)", baris.strip())
            if cocok:
                mac, nama = cocok.group(1), cocok.group(2)
                perangkat.setdefault(mac, {"mac": mac, "nama": nama})
                perangkat[mac]["dikenal"] = perangkat[mac].get("dikenal", False) or dikenal
    for mac, p in perangkat.items():
        ok, info = _jalankan(["bluetoothctl", "info", mac])
        p["terhubung"] = "Connected: yes" in info
        p["tepercaya"] = "Trusted: yes" in info
        p["audio"] = "Audio Sink" in info or "audio-" in info
    # Yang sudah tersambung ditaruh paling atas, lalu yang sudah dikenal.
    return sorted(perangkat.values(),
                  key=lambda p: (not p["terhubung"], not p.get("dikenal"), p["nama"]))


def bluetooth_aksi(mac: str, aksi: str) -> tuple[bool, str]:
    if not re.fullmatch(r"[0-9A-F:]{17}", mac.upper()):
        return False, "alamat MAC tidak sah"
    mac = mac.upper()
    if aksi == "sambung":
        # Pair boleh gagal kalau sudah pernah dipasangkan; yang menentukan
        # keberhasilan tetap langkah connect.
        _jalankan(["bluetoothctl", "--timeout", "6", "scan", "on"], 12)
        _jalankan(["bluetoothctl", "pair", mac], 25)
        _jalankan(["bluetoothctl", "trust", mac])
        ok, keluar = _jalankan(["bluetoothctl", "connect", mac], 25)
        return ok, keluar.splitlines()[-1] if keluar else ""
    if aksi == "putus":
        return _jalankan(["bluetoothctl", "disconnect", mac], 15)
    if aksi == "lupakan":
        return _jalankan(["bluetoothctl", "remove", mac], 15)
    return False, f"aksi tidak dikenal: {aksi}"


def audio_sekarang() -> str:
    ok, keluar = _jalankan(["wpctl", "inspect", "@DEFAULT_AUDIO_SINK@"], 8)
    if not ok:
        return "tidak ada keluaran audio"
    cocok = re.search(r'node\.description = "([^"]+)"', keluar)
    return cocok.group(1) if cocok else "keluaran audio aktif"


# --- WiFi --------------------------------------------------------------------
def wifi_daftar() -> list[dict]:
    ok, keluar = _jalankan(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY",
                            "device", "wifi", "list"], 15)
    if not ok:
        return []
    jaringan: dict[str, dict] = {}
    for baris in keluar.splitlines():
        bagian = baris.split(":")
        if len(bagian) < 4 or not bagian[1]:
            continue
        ssid = bagian[1]
        data = {"ssid": ssid, "aktif": bagian[0] == "*",
                "sinyal": int(bagian[2]) if bagian[2].isdigit() else 0,
                "aman": bool(bagian[3].strip())}
        # SSID yang sama bisa muncul dari beberapa titik akses; ambil terkuat.
        if ssid not in jaringan or data["sinyal"] > jaringan[ssid]["sinyal"]:
            jaringan[ssid] = data
    return sorted(jaringan.values(), key=lambda j: (-j["aktif"], -j["sinyal"]))


def wifi_sambung(ssid: str, sandi: str) -> tuple[bool, str]:
    if not ssid:
        return False, "SSID kosong"
    perintah = ["sudo", "-n", "nmcli", "device", "wifi", "connect", ssid]
    if sandi:
        perintah += ["password", sandi]
    ok, keluar = _jalankan(perintah, 45)
    # Jangan pernah memantulkan sandi kembali ke halaman web.
    return ok, keluar.replace(sandi, "***") if sandi else keluar


# --- sistem ------------------------------------------------------------------
def info_sistem() -> dict:
    info: dict[str, str] = {}
    ok, suhu = _jalankan(["vcgencmd", "measure_temp"], 5)
    info["suhu"] = suhu.replace("temp=", "") if ok else "-"
    ok, alamat = _jalankan(["hostname", "-I"], 5)
    info["alamat"] = alamat.strip() if ok else "-"
    try:
        with open("/proc/uptime") as f:
            detik = float(f.read().split()[0])
        info["nyala"] = f"{int(detik // 3600)} jam {int(detik % 3600 // 60)} menit"
    except OSError:
        info["nyala"] = "-"
    info["audio"] = audio_sekarang()
    return info


def sistem_aksi(aksi: str) -> tuple[bool, str]:
    if aksi == "matikan":
        return _jalankan(["sudo", "-n", "poweroff"], 10)
    if aksi == "reboot":
        return _jalankan(["sudo", "-n", "reboot"], 10)
    return False, f"aksi tidak dikenal: {aksi}"
