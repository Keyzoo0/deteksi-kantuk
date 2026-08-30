"""Membuat ulang berkas suara asisten (folder `suara/`) dengan TTS neural.

Suara diambil dari Microsoft Edge TTS (`edge-tts`) memakai voice Bahasa
Indonesia `id-ID-GadisNeural` / `id-ID-ArdiNeural`, lalu disimpan sebagai WAV
mono 22 kHz. Hasilnya ikut masuk repo sehingga program **tidak** perlu internet
maupun TTS apa pun saat berjalan -- peringatan tinggal diputar.

Skrip ini hanya diperlukan bila ingin mengubah kalimatnya. Butuh internet dan
dua paket tambahan yang tidak dipakai program utama:

    uv pip install edge-tts soundfile      # atau: pip install edge-tts soundfile
    python tools/buat_suara.py

Ubah kalimat lewat `--teks kunci="kalimat baru"`, mis.:

    python tools/buat_suara.py --hanya mengantuk \
        --teks mengantuk="Bapak sudah mengantuk, tolong menepi"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
KELUARAN = AKAR / "suara"

sys.path.insert(0, str(AKAR))

# Kalimatnya tinggal di src/suara.py supaya TTS cadangan mengucapkan hal yang
# persis sama dengan berkas WAV di sini. Nama berkas: "<kunci>-<suara>.wav".
from src.suara import (BIP, BIP_GANDA, PESAN, SIRENE,    # noqa: E402
                       TANPA_VOICE)

SUARA = {"gadis": "id-ID-GadisNeural", "ardi": "id-ID-ArdiNeural"}
LAJU = "-5%"          # sedikit lebih lambat -- lebih jelas di dalam mobil
CUPLIK = 22050        # 22 kHz mono sudah cukup untuk suara, berkasnya kecil


async def buat(teks: str, voice: str, tujuan: Path, rate: str) -> None:
    import edge_tts
    import numpy as np
    import soundfile as sf

    sementara = tujuan.with_suffix(".mp3")
    await edge_tts.Communicate(teks, voice, rate=rate).save(str(sementara))
    try:
        data, sr = sf.read(str(sementara), dtype="float32", always_2d=True)
        mono = data.mean(axis=1)
        if sr != CUPLIK:
            idx = np.linspace(0, len(mono) - 1, int(len(mono) * CUPLIK / sr))
            mono = np.interp(idx, np.arange(len(mono)), mono)
        # Normalisasi supaya semua pesan sama kerasnya di speaker mobil.
        mono = mono / (float(np.max(np.abs(mono))) or 1.0) * 0.95
        sf.write(str(tujuan), (mono * 32767).astype("int16"), CUPLIK, subtype="PCM_16")
    finally:
        sementara.unlink(missing_ok=True)
    print(f"  {tujuan.relative_to(AKAR)}  ({len(mono) / CUPLIK:.1f} detik)")


def _nada(potongan: list[tuple[float, float]]) -> "object":
    """Rangkai (frekuensi Hz, durasi detik); frekuensi 0 berarti hening."""
    import numpy as np

    bagian = []
    tepi = int(0.005 * CUPLIK)                 # 5 ms naik-turun, agar tak "klik"
    for f, d in potongan:
        n = int(CUPLIK * d)
        if f <= 0:
            bagian.append(np.zeros(n, dtype="float32"))
            continue
        t = np.arange(n) / CUPLIK
        gel = np.sin(2 * np.pi * f * t).astype("float32")
        gel[:tepi] *= np.linspace(0, 1, tepi)
        gel[-tepi:] *= np.linspace(1, 0, tepi)
        bagian.append(gel)
    return np.concatenate(bagian)


def _simpan_nada(tujuan: Path, potongan: list[tuple[float, float]]) -> None:
    import numpy as np
    import soundfile as sf

    nada = _nada(potongan) * 0.9
    sf.write(str(tujuan), (nada * 32767).astype("int16"), CUPLIK, subtype="PCM_16")
    print(f"  {tujuan.relative_to(AKAR)}  ({len(nada) / CUPLIK:.2f} detik)")


def buat_sirene(tujuan: Path, detik: float = 4.0) -> None:
    """Nada alarm dua-nada, dibuat langsung (bukan TTS, tidak perlu internet).

    Dipakai alarm tingkat 2 yang berbunyi menerus sampai tombol ditekan.
    Dua nada bergantian jauh lebih menusuk daripada satu nada datar, dan
    frekuensinya (800/1000 Hz) sengaja di rentang paling peka telinga
    manusia sekaligus mudah dikeluarkan speaker kecil.
    """
    import numpy as np
    import soundfile as sf

    n = int(CUPLIK * detik)
    t = np.arange(n) / CUPLIK
    nada = np.zeros(n, dtype="float32")
    potong = 0.25                                  # panjang tiap nada, detik
    for i in range(int(detik / potong)):
        a, b = int(i * potong * CUPLIK), int((i + 1) * potong * CUPLIK)
        f = 800.0 if i % 2 == 0 else 1000.0
        nada[a:b] = np.sin(2 * np.pi * f * t[a:b])
    # Amplop naik-turun 5 ms di tiap ujung potongan supaya tidak "klik".
    tepi = int(0.005 * CUPLIK)
    amplop = np.ones(n, dtype="float32")
    for i in range(int(detik / potong)):
        a, b = int(i * potong * CUPLIK), int((i + 1) * potong * CUPLIK)
        amplop[a:a + tepi] = np.linspace(0, 1, tepi)
        amplop[b - tepi:b] = np.linspace(1, 0, tepi)
    nada = (nada * amplop * 0.9 * 32767).astype("int16")
    sf.write(str(tujuan), nada, CUPLIK, subtype="PCM_16")
    print(f"  {tujuan.relative_to(AKAR)}  ({detik:.1f} detik, nada 800/1000 Hz)")


async def semua(pesan: dict[str, str], suara: dict[str, str], rate: str) -> None:
    KELUARAN.mkdir(parents=True, exist_ok=True)
    for kunci, teks in pesan.items():
        if kunci in TANPA_VOICE:
            if kunci == SIRENE:
                buat_sirene(KELUARAN / f"{kunci}.wav")
            elif kunci == BIP:
                _simpan_nada(KELUARAN / f"{kunci}.wav", [(1200, 0.14)])
            elif kunci == BIP_GANDA:
                _simpan_nada(KELUARAN / f"{kunci}.wav",
                             [(1200, 0.12), (0, 0.08), (1200, 0.12)])
            continue
        for nama, voice in suara.items():
            await buat(teks, voice, KELUARAN / f"{kunci}-{nama}.wav", rate)


def main() -> int:
    p = argparse.ArgumentParser(description="Buat ulang berkas suara asisten.")
    p.add_argument("--hanya", nargs="*", choices=sorted(PESAN),
                   help="hanya kunci pesan tertentu (default: semua)")
    p.add_argument("--suara", nargs="*", choices=sorted(SUARA),
                   help="hanya voice tertentu (default: gadis dan ardi)")
    p.add_argument("--teks", nargs="*", default=[], metavar="KUNCI=KALIMAT",
                   help="ganti kalimat satu pesan")
    # "%" harus dituliskan ganda: argparse memakai teks help sebagai template.
    p.add_argument("--laju", default=LAJU,
                   help=f"kecepatan bicara, mis. -10%% (default {LAJU.replace('%', '%%')})")
    arg = p.parse_args()

    pesan = dict(PESAN)
    for isian in arg.teks:
        kunci, _, teks = isian.partition("=")
        if kunci not in pesan:
            print(f"kunci tidak dikenal: {kunci} (pilihan: {', '.join(pesan)})")
            return 2
        pesan[kunci] = teks
    if arg.hanya:
        pesan = {k: v for k, v in pesan.items() if k in arg.hanya}
    suara = {k: v for k, v in SUARA.items() if not arg.suara or k in arg.suara}

    try:
        import edge_tts        # noqa: F401
        import soundfile       # noqa: F401
    except ImportError:
        print("Butuh paket tambahan (dan internet):\n"
              "  uv pip install edge-tts soundfile", file=sys.stderr)
        return 1

    jumlah = sum(1 if k in TANPA_VOICE else len(suara) for k in pesan)
    print(f"Membuat {jumlah} berkas di {KELUARAN}/")
    asyncio.run(semua(pesan, suara, arg.laju))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
