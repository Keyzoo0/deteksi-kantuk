"""Ukur kontras warna antarmuka web di tema terang dan gelap.

Halaman dipakai di atas motor, sering di bawah matahari langsung, jadi teks
yang kontrasnya tipis praktis hilang. Skrip ini membaca CSS hasil build
(`web/dist`), meresolusi token tema, menumpuk warna semitransparan ke
latarnya, lalu menghitung rasio kontras WCAG.

Ambang yang dipakai: 4,5 untuk teks biasa, 3,0 untuk teks besar/tebal dan
untuk elemen grafis (garis grafik, batas kotak).

Pemeriksaan ini hanya membaca CSS, jadi cepat dan tidak butuh npm. Untuk
audit yang mengukur halaman yang benar-benar dirender (termasuk teks yang
warnanya baru terbentuk saat runtime), pakai `tools/cek_kontras_web.mjs`.

Jalankan: .venv/bin/python tools/cek_warna.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
TEKS, BESAR = 4.5, 3.0


def _blok(css: str) -> list[tuple[str, str]]:
    """Pasangan (pemilih, isi) untuk tiap blok CSS, termasuk yang bersarang."""
    hasil, dalam, i = [], 0, 0
    while True:
        buka = css.find("{", i)
        if buka < 0:
            return hasil
        tutup, dalam, j = -1, 1, buka + 1
        while j < len(css) and dalam:
            dalam += (css[j] == "{") - (css[j] == "}")
            if not dalam:
                tutup = j
            j += 1
        if tutup < 0:
            return hasil
        pemilih = re.split(r"[};]", css[:buka])[-1].strip()
        hasil.append((pemilih, css[buka + 1:tutup]))
        hasil += _blok(css[buka + 1:tutup])
        i = tutup + 1


def token(css: str) -> tuple[dict, dict]:
    """(token tema terang, token tema gelap) dari seluruh blok CSS."""
    terang, gelap = {}, {}
    for pemilih, isi in _blok(css):
        tujuan = gelap if ".dark" in pemilih else terang if ":root" in pemilih or ":host" in pemilih else None
        if tujuan is None:
            continue
        for nama, nilai in re.findall(r"(--[\w-]+)\s*:\s*([^;{}]+)", isi):
            tujuan[nama] = nilai.strip()
    return terang, {**terang, **gelap}       # tema gelap mewarisi token terang


def _oklch(l: float, c: float, h: float) -> tuple[float, float, float]:
    import math
    a, b = c * math.cos(math.radians(h)), c * math.sin(math.radians(h))
    l_, m_, s_ = (l + 0.3963377774 * a + 0.2158037573 * b,
                  l - 0.1055613458 * a - 0.0638541728 * b,
                  l - 0.0894841775 * a - 1.2914855480 * b)
    l3, m3, s3 = l_ ** 3, m_ ** 3, s_ ** 3
    return (+4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3,
            -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3,
            -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3)


def warna(nilai: str, tema: dict, sisa: int = 8) -> tuple[float, float, float, float]:
    """Nilai CSS -> (r, g, b linear, alfa). Mengikuti var() bila perlu."""
    nilai = nilai.strip()
    if sisa <= 0:
        raise ValueError("var() melingkar")
    var = re.fullmatch(r"var\((--[\w-]+)(?:,([^)]*))?\)", nilai)
    if var:
        nama, cadangan = var.group(1), var.group(2)
        if nama in tema:
            return warna(tema[nama], tema, sisa - 1)
        if cadangan:
            return warna(cadangan, tema, sisa - 1)
        raise KeyError(nama)
    ok = re.fullmatch(r"oklch\(\s*([\d.]+%?)\s+([\d.]+%?)\s+([\d.]+)\s*(?:/\s*([\d.]+%?)\s*)?\)", nilai)
    if ok:
        angka = lambda s, skala=1.0: (float(s[:-1]) / 100 * skala if s.endswith("%") else float(s))
        l, c, h = angka(ok.group(1)), angka(ok.group(2)), float(ok.group(3))
        alfa = angka(ok.group(4), 1.0) if ok.group(4) else 1.0
        return (*_oklch(l, c, h), alfa)
    raise ValueError(f"format warna tidak dikenal: {nilai}")


def tumpuk(lapisan: list[tuple[str, float]], tema: dict) -> tuple[float, float, float]:
    """Tumpuk warna (dari paling bawah) dengan alfa masing-masing."""
    dasar = None
    for nilai, alfa in lapisan:
        r, g, b, a = warna(nilai, tema)
        a *= alfa
        dasar = (r, g, b) if dasar is None else tuple(k * a + d * (1 - a) for k, d in zip((r, g, b), dasar))
    return dasar


def luminansi(rgb: tuple[float, float, float]) -> float:
    jepit = lambda x: min(1.0, max(0.0, x))
    return sum(k * jepit(v) for k, v in zip((0.2126, 0.7152, 0.0722), rgb))


def kontras(depan: list[tuple[str, float]], belakang: list[tuple[str, float]], tema: dict) -> float:
    a, b = luminansi(tumpuk(belakang + depan, tema)), luminansi(tumpuk(belakang, tema))
    terang, gelap = max(a, b), min(a, b)
    return (terang + 0.05) / (gelap + 0.05)


# (nama, warna teks/garis, tumpukan latar, ambang). Latar selalu dimulai dari
# --background karena kartu dan panel semuanya digambar di atasnya.
LATAR = ("var(--background)", 1.0)
KARTU = [LATAR, ("var(--card)", 1.0)]
KARTU_ISI = KARTU + [("var(--muted)", 0.4)]      # kartu kecil: bg-muted/40

PERIKSA = [
    ("teks utama di halaman", ("var(--foreground)", 1.0), [LATAR], TEKS),
    ("teks utama di panel", ("var(--card-foreground)", 1.0), KARTU, TEKS),
    ("teks redup di panel", ("var(--muted-foreground)", 1.0), KARTU, TEKS),
    ("nilai di kartu kecil", ("var(--card-foreground)", 1.0), KARTU_ISI, TEKS),
    ("label di kartu kecil", ("var(--card-foreground)", 1.0), KARTU_ISI, TEKS),
    ("lencana AMAN", ("var(--color-emerald-700)", 1.0), KARTU + [("var(--color-emerald-500)", 0.1)], TEKS),
    ("lencana KANTUK", ("var(--color-red-800)", 1.0), KARTU + [("var(--destructive)", 0.15)], TEKS),
    ("lencana tanpa wajah", ("var(--color-amber-700)", 1.0), KARTU + [("var(--color-amber-500)", 0.1)], TEKS),
    ("lencana alarm tingkat 3", ("var(--color-red-900)", 1.0), KARTU + [("var(--destructive)", 0.25)], TEKS),
    ("teks peringatan kuning", ("var(--color-amber-800)", 1.0), KARTU + [("var(--color-amber-500)", 0.1)], TEKS),
    ("garis grafik EAR", ("var(--garis-ear)", 1.0), KARTU, BESAR),
    ("garis grafik PERCLOS", ("var(--garis-perclos)", 1.0), KARTU, BESAR),
    ("tombol tema (ikon)", ("var(--muted-foreground)", 1.0), [LATAR], BESAR),
]
# Di tema gelap warna tulisannya lebih terang; padanannya di sini.
GELAP = {
    "var(--color-emerald-700)": "var(--color-emerald-400)",
    "var(--color-amber-700)": "var(--color-amber-300)",
    "var(--color-red-800)": "var(--color-red-300)",
    "var(--color-red-900)": "var(--color-red-200)",
    "var(--color-amber-800)": "var(--color-amber-200)",
}


def main() -> int:
    css = sorted((AKAR / "web/dist/assets").glob("index-*.css"))
    if not css:
        print("web/dist belum dibangun -- jalankan: cd web && npm run build")
        return 2
    terang, gelap = token(css[-1].read_text(encoding="utf-8"))
    print(f"Berkas   : {css[-1].relative_to(AKAR)}")
    gagal = 0
    for nama_tema, tema, alih in (("TERANG", terang, False), ("GELAP", gelap, True)):
        print(f"\n{nama_tema}\n{'-' * 58}")
        for nama, depan, belakang, ambang in PERIKSA:
            nilai, alfa = depan
            if alih:
                nilai = GELAP.get(nilai, nilai)
            r = kontras([(nilai, alfa)], belakang, tema)
            ok = r >= ambang
            gagal += not ok
            print(f"  [{'LULUS' if ok else 'GAGAL'}] {nama:<28} {r:5.2f} : 1  (min {ambang})")
    print(f"\n{'=' * 58}")
    print("Semua kontras memenuhi ambang." if not gagal else f"{gagal} pasangan warna di bawah ambang.")
    return 0 if not gagal else 1


if __name__ == "__main__":
    sys.exit(main())
