"""Mendaftarkan kerabat penerima notifikasi Telegram.

Bot Telegram tidak bisa mengirim pesan lebih dulu ke orang yang belum pernah
menyapanya. Jadi alurnya:

    1. Minta kerabat membuka bot Anda lalu menekan START (atau kirim /start).
    2. Jalankan skrip ini: pengirim yang terbaca akan ditampilkan.
    3. Pilih nomor yang disetujui; chat id-nya disimpan ke rahasia.json.

Jalankan: .venv/bin/python tools/daftar_kerabat.py
          .venv/bin/python tools/daftar_kerabat.py --uji     (kirim pesan coba)
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
API = "https://api.telegram.org/bot{token}/{metode}"


def panggil(token: str, metode: str, data: dict | None = None) -> dict:
    url = API.format(token=token, metode=metode)
    badan = urllib.parse.urlencode(data).encode() if data else None
    with urllib.request.urlopen(url, badan, timeout=20) as r:
        return json.load(r)


def main() -> int:
    p = argparse.ArgumentParser(description="Daftarkan kerabat penerima notifikasi.")
    p.add_argument("--rahasia", default=str(AKAR / "rahasia.json"))
    p.add_argument("--uji", action="store_true", help="kirim pesan percobaan ke semua kerabat")
    arg = p.parse_args()

    berkas = Path(arg.rahasia)
    try:
        rahasia = json.loads(berkas.read_text(encoding="utf-8"))
    except OSError:
        print(f"{berkas} belum ada. Buat berisi: "
              '{"telegram_token": "...", "telegram_chat_id": []}', file=sys.stderr)
        return 1
    token = rahasia.get("telegram_token", "").strip()
    if not token:
        print("telegram_token belum diisi.", file=sys.stderr)
        return 1

    terdaftar = [int(c) for c in rahasia.get("telegram_chat_id", [])]
    bot = panggil(token, "getMe")["result"]
    print(f"Bot        : {bot['first_name']} @{bot['username']}")
    print(f"Terdaftar  : {terdaftar or '(belum ada)'}")

    if arg.uji:
        if not terdaftar:
            print("Belum ada kerabat untuk dikirimi.")
            return 1
        for chat in terdaftar:
            hasil = panggil(token, "sendMessage", {
                "chat_id": chat,
                "text": "Uji coba dari alat deteksi kantuk. Kalau pesan ini sampai, "
                        "notifikasi darurat nanti juga akan sampai."})
            print(f"  {chat}: {'terkirim' if hasil.get('ok') else hasil.get('description')}")
        return 0

    # Pesan lama hanya tersimpan 24 jam di server Telegram; kalau kosong,
    # kerabat cukup menyapa botnya lagi.
    pembaruan = panggil(token, "getUpdates")["result"]
    kandidat: dict[int, str] = {}
    for u in pembaruan:
        pesan = u.get("message") or u.get("edited_message") or {}
        chat = pesan.get("chat") or {}
        if chat.get("id") and chat["id"] not in terdaftar:
            nama = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x)
            kandidat[chat["id"]] = nama or chat.get("title") or str(chat["id"])

    if not kandidat:
        print("\nBelum ada pengirim baru. Minta kerabat menekan START di "
              f"https://t.me/{bot['username']} lalu jalankan skrip ini lagi.")
        return 0

    print("\nPengirim baru:")
    urut = list(kandidat.items())
    for i, (chat, nama) in enumerate(urut, 1):
        print(f"  {i}. {nama}  (chat id {chat})")
    pilih = input("Nomor yang disetujui (pisahkan koma, kosong = batal): ").strip()
    if not pilih:
        return 0
    for bagian in pilih.split(","):
        if bagian.strip().isdigit() and 1 <= int(bagian) <= len(urut):
            terdaftar.append(urut[int(bagian) - 1][0])

    rahasia["telegram_chat_id"] = sorted(set(terdaftar))
    berkas.write_text(json.dumps(rahasia, indent=2) + "\n", encoding="utf-8")
    berkas.chmod(0o600)
    print(f"Tersimpan. Kerabat terdaftar sekarang: {rahasia['telegram_chat_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
