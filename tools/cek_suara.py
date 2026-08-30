"""Utilitas: dengarkan pesan asisten suara tanpa perlu mengantuk dulu.

Memutar tiap pesan sesuai konfigurasi -- berguna untuk memastikan speaker,
volume, dan pemutar audionya benar sebelum dipakai di jalan.

Jalankan: .venv/bin/python tools/cek_suara.py
          .venv/bin/python tools/cek_suara.py --pesan mengantuk
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AKAR))

from src.config import Config                        # noqa: E402
from src.suara import PESAN, AsistenSuara            # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Uji pesan asisten suara.")
    p.add_argument("--config", default=str(AKAR / "config.json"))
    p.add_argument("--pesan", nargs="*", choices=sorted(PESAN),
                   help="uji pesan tertentu saja (default: semua)")
    arg = p.parse_args()

    cfg = Config.muat(arg.config)
    cfg.suara.aktif = True                      # abaikan "aktif": false saat menguji
    asisten = AsistenSuara(cfg.suara, AKAR)
    print(f"Sumber suara : {asisten.keterangan}")
    if not asisten.aktif:
        print("Tidak ada cara memutar suara di sistem ini.")
        return 1

    for kunci in (arg.pesan or list(PESAN)):
        print(f'  {kunci:<16} "{PESAN[kunci]}"')
        asisten.ucap(kunci, paksa=True)
        while asisten.sedang_bicara:            # tunggu sampai selesai berbunyi
            time.sleep(0.1)
        time.sleep(0.4)

    print('Selesai. Tidak terdengar? Cek volume, atau setel "pemutar" di config.json.')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
