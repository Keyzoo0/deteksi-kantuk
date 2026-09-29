import { useEffect, useRef, useState } from "react"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Panel, TautanUnduh } from "@/komponen/bagian"
import { ambil } from "@/lib/api"

// Label aksi sama persis dengan kolom `aksi` di CSV, supaya yang terlihat di
// layar bisa dicocokkan langsung dengan berkasnya. Warnanya token tema
// (index.css) yang punya nilai sendiri untuk terang dan gelap.
const WARNA_AKSI = {
  "menyalakan": "var(--aksi-nyala)",
  "mematikan": "var(--aksi-mati)",
  "matikan alarm": "var(--aksi-alarm)",
}
const warnaAksi = (aksi) => WARNA_AKSI[aksi] || "var(--aksi-netral)"
const LEGENDA = [["menyalakan", "menyalakan"], ["mematikan", "mematikan"],
                 ["matikan alarm", "matikan alarm"], ["ketuk", "lainnya"]]

// [label, panjang jendela, jarak garis waktu] dalam detik.
const JENDELA = [["2 jam", 7200, 1200], ["30 mnt", 1800, 300], ["5 mnt", 300, 60]]

// Jam alat (WIB), bukan jam HP: halaman bisa saja dibuka dari zona lain.
const fmtMenit = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Jakarta", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
const fmtDetik = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Jakarta", hour: "2-digit", minute: "2-digit", second: "2-digit",
  hourCycle: "h23" })
const jamMenit = (t) => fmtMenit.format(new Date(t * 1000))
const jamDetik = (t) => fmtDetik.format(new Date(t * 1000))
const dtk = (x) => x.toLocaleString("id-ID", { minimumFractionDigits: 1, maximumFractionDigits: 1 })

// Keadaan langsung diambil dari rute ringan /tombol 4x per detik. /data cuma
// diambil tiap 2 detik dan terlalu besar untuk dipercepat -- tekanan singkat
// tidak akan sempat terlihat "DITEKAN" di sana.
function useTombolLangsung() {
  const [langsung, setLangsung] = useState(null)
  useEffect(() => {
    let hidup = true
    let sibuk = false
    const tarik = () => {
      if (sibuk) return             // jaringan lambat: jangan menumpuk permintaan
      sibuk = true
      ambil("/tombol").then((d) => hidup && setLangsung(d)).catch(() => {})
        .finally(() => { sibuk = false })
    }
    tarik()
    const pewaktu = setInterval(tarik, 250)
    return () => { hidup = false; clearInterval(pewaktu) }
  }, [])
  return langsung
}

function Titik({ warna, kelas = "size-2" }) {
  return <span className={`inline-block shrink-0 rounded-full ${kelas}`} style={{ background: warna }} />
}

function LencanaTekan({ langsung }) {
  const ditekan = langsung?.ditekan
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-semibold
                      ${ditekan ? "border-amber-500/40 bg-amber-500/15 text-amber-800 dark:text-amber-200"
                                : "border-border text-muted-foreground"}`}>
      <span className={`size-2 rounded-full ${ditekan ? "animate-pulse bg-amber-500" : "bg-muted-foreground/50"}`} />
      {ditekan ? "DITEKAN" : "dilepas"}
    </span>
  )
}

// Bilah progres tahan dengan penanda di kedua ambang: kelihatan berapa lagi
// menuju menyalakan (3 dtk, saat siaga) atau mematikan (8 dtk, saat menyala).
function BilahTahan({ langsung }) {
  if (!langsung) {
    return <div className="h-[58px] animate-pulse rounded-md bg-muted/60" />
  }
  if (!langsung.ada) {
    return (
      <p className="rounded-md border border-dashed px-3 py-3 text-sm text-muted-foreground">
        GPIO tombol tidak tersedia di perangkat ini. Log di bawah tetap menampilkan
        tekanan yang sempat tercatat.
      </p>
    )
  }
  const { ditekan, lama, ambang, ambang_nyala, ambang_mati, keadaan } = langsung
  const maks = ambang_mati + 2
  const menuju = keadaan === "siaga" ? "menyalakan" : "mematikan"
  const tercapai = ditekan && lama >= ambang
  const isi = ditekan ? Math.min(100, (lama / maks) * 100) : 0
  const keterangan = !ditekan
    ? `tahan ${ambang} dtk untuk ${menuju}`
    : tercapai ? `lepaskan sekarang untuk ${menuju}`
               : `${dtk(ambang - lama)} dtk lagi untuk ${menuju}`
  const penanda = [[ambang_nyala, "nyalakan", keadaan === "siaga"],
                   [ambang_mati, "matikan", keadaan !== "siaga"]]

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <span className="text-sm font-semibold tabular-nums">
          {ditekan ? `Ditahan ${dtk(lama)} dtk` : "Tombol dilepas"}
        </span>
        <span className={`text-xs ${tercapai ? "font-semibold text-foreground" : "text-muted-foreground"}`}>
          {keterangan}
        </span>
      </div>
      <div className="relative h-2.5 rounded-full bg-muted">
        <div className="h-full rounded-full transition-[width] duration-200 ease-linear"
             style={{ width: `${isi}%`,
                      background: tercapai ? warnaAksi(menuju) : "var(--aksi-netral)" }} />
        {penanda.map(([detik, , aktif]) => (
          <span key={detik}
                className={`absolute -top-1 h-[18px] w-0.5 -translate-x-1/2 rounded-full
                            ${aktif ? "bg-foreground" : "bg-muted-foreground/40"}`}
                style={{ left: `${(detik / maks) * 100}%` }} />
        ))}
      </div>
      <div className="relative mt-1.5 h-4 text-[11px]">
        {penanda.map(([detik, nama, aktif]) => (
          <span key={detik}
                className={`absolute -translate-x-1/2 whitespace-nowrap
                            ${aktif ? "font-semibold text-foreground" : "text-muted-foreground"}`}
                style={{ left: `${(detik / maks) * 100}%` }}>
            {detik} dtk · {nama}
          </span>
        ))}
      </div>
    </div>
  )
}

// Grafik high/low digambar sendiri dengan SVG. Di sumbu 2 jam, tekanan 8
// detik proporsionalnya cuma ~1,5 px dan ketukan tidak kelihatan sama sekali,
// jadi tiap pulsa diberi lebar minimum; durasi tepatnya ada di tooltip & tabel.
function GrafikTombol({ log, langsung, sekarang, jendela, langkah, labelJendela }) {
  const wadah = useRef(null)
  const [lebar, setLebar] = useState(0)
  const [sorot, setSorot] = useState(null)       // waktu lepas pulsa yang disorot

  useEffect(() => {
    const amati = new ResizeObserver(([e]) => setLebar(e.contentRect.width))
    amati.observe(wadah.current)
    return () => amati.disconnect()
  }, [])

  const TINGGI = 132, KIRI = 58, KANAN = 12, ATAS = 14, BAWAH = 26, MIN_PX = 4
  const lebarPlot = Math.max(1, lebar - KIRI - KANAN)
  const awal = sekarang - jendela
  const x = (t) => KIRI + ((t - awal) / jendela) * lebarPlot
  const yAtas = ATAS
  const yBawah = TINGGI - BAWAH

  const pulsa = log
    .filter(([lepas]) => lepas >= awal)
    .map(([lepas, lama, aksi, keadaan]) => {
      const tengah = (x(lepas - lama) + x(lepas)) / 2
      const lebarP = Math.max(MIN_PX, x(lepas) - x(lepas - lama))
      return { lepas, lama, aksi, keadaan,
               x0: Math.max(KIRI, tengah - lebarP / 2),
               x1: Math.min(KIRI + lebarPlot, tengah + lebarP / 2) }
    })

  let berjalan = null
  if (langsung?.ditekan) {
    const x1 = x(sekarang)
    const lebarP = Math.max(MIN_PX, x1 - x(sekarang - langsung.lama))
    const tercapai = langsung.lama >= langsung.ambang
    berjalan = { x0: Math.max(KIRI, x1 - lebarP), x1,
                 warna: tercapai ? warnaAksi(langsung.keadaan === "siaga" ? "menyalakan" : "mematikan")
                                 : "var(--aksi-netral)" }
  }

  const garis = []
  for (let t = Math.ceil(awal / langkah) * langkah; t <= sekarang; t += langkah) garis.push(t)

  const disorot = pulsa.find((p) => p.lepas === sorot)

  return (
    <div ref={wadah} className="relative w-full" onMouseLeave={() => setSorot(null)}>
      {lebar > 0 && (
        <svg width={lebar} height={TINGGI} className="block select-none" role="img"
             aria-label={`Grafik tekanan tombol ${labelJendela} terakhir`}>
          {garis.map((t) => (
            <line key={t} x1={x(t)} x2={x(t)} y1={yAtas - 4} y2={yBawah}
                  className="stroke-border" strokeDasharray="2 4" />
          ))}
          <text x={KIRI - 10} y={yAtas + 1} textAnchor="end" dominantBaseline="middle"
                className="fill-muted-foreground text-[11px]">ditekan</text>
          <text x={KIRI - 10} y={yBawah} textAnchor="end" dominantBaseline="middle"
                className="fill-muted-foreground text-[11px]">dilepas</text>
          <line x1={KIRI} x2={KIRI + lebarPlot} y1={yBawah} y2={yBawah}
                className="stroke-muted-foreground/70" strokeWidth={1.5} />
          {pulsa.map((p) => (
            <rect key={p.lepas} x={p.x0} y={yAtas} width={p.x1 - p.x0} height={yBawah - yAtas}
                  rx={1.5} fill={warnaAksi(p.aksi)} fillOpacity={sorot === p.lepas ? 0.6 : 0.3}
                  stroke={warnaAksi(p.aksi)} strokeWidth={1.5}
                  onMouseEnter={() => setSorot(p.lepas)} />
          ))}
          {berjalan && (
            <rect x={berjalan.x0} y={yAtas} width={berjalan.x1 - berjalan.x0}
                  height={yBawah - yAtas} rx={1.5} fill={berjalan.warna} fillOpacity={0.45}
                  stroke={berjalan.warna} strokeWidth={1.5} className="animate-pulse" />
          )}
          {garis.map((t) => (
            <text key={`j${t}`} x={x(t)} y={TINGGI - 6} textAnchor="middle"
                  className="fill-muted-foreground text-[11px] tabular-nums">{jamMenit(t)}</text>
          ))}
        </svg>
      )}
      {!pulsa.length && !berjalan && lebar > 0 && (
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-center
                        text-xs text-muted-foreground" style={{ height: yBawah, paddingLeft: KIRI }}>
          belum ada tekanan dalam {labelJendela} terakhir
        </div>
      )}
      {disorot && (
        <div className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md
                        border bg-popover px-2.5 py-1.5 text-xs shadow-md"
             style={{ left: Math.min(Math.max((disorot.x0 + disorot.x1) / 2, 70), lebar - 70),
                      top: yAtas - 6 }}>
          <p className="font-semibold tabular-nums">{jamDetik(disorot.lepas - disorot.lama)}</p>
          <p className="flex items-center gap-1.5 whitespace-nowrap text-muted-foreground">
            <Titik warna={warnaAksi(disorot.aksi)} />
            {dtk(disorot.lama)} dtk · {disorot.aksi}
          </p>
        </div>
      )}
    </div>
  )
}

export default function PanelTombol({ tombol }) {
  const langsung = useTombolLangsung()
  const [pilihan, setPilihan] = useState(0)
  const [labelJendela, jendela, langkah] = JENDELA[pilihan]
  const log = tombol?.log || []
  const sekarang = langsung?.sekarang ?? tombol?.sekarang
  const baris = log.slice().reverse()

  return (
    <Panel judul="Tombol — 2 jam terakhir" kelas="xl:col-span-12"
      aksi={<div className="flex items-center gap-2">
        <LencanaTekan langsung={langsung} />
        <TautanUnduh href="/ekspor-tombol.csv"
                     judul="Log tombol 2 jam terakhir: waktu tekan & lepas, durasi, aksi, keadaan sistem">
          CSV tombol
        </TautanUnduh>
      </div>}>
      <BilahTahan langsung={langsung} />

      <div className="mt-5 mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {LEGENDA.map(([aksi, nama]) => (
            <span key={nama} className="flex items-center gap-1.5">
              <Titik warna={warnaAksi(aksi)} kelas="size-2 rounded-[2px]" />{nama}
            </span>
          ))}
          <span className="tabular-nums">· {log.length} tekanan</span>
        </div>
        <div className="inline-flex rounded-md border p-0.5" role="group" aria-label="Rentang grafik">
          {JENDELA.map(([label], i) => (
            <button key={label} type="button" onClick={() => setPilihan(i)} aria-pressed={pilihan === i}
                    className={`rounded px-2 py-0.5 text-xs transition-colors
                                ${pilihan === i ? "bg-muted font-semibold text-foreground"
                                                : "text-muted-foreground hover:text-foreground"}`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {sekarang ? (
        <GrafikTombol log={log} langsung={langsung} sekarang={sekarang} jendela={jendela}
                      langkah={langkah} labelJendela={labelJendela} />
      ) : (
        <div className="h-[132px] animate-pulse rounded-md bg-muted/60" />
      )}

      <div className="mt-3 max-h-56 overflow-y-auto rounded-md border">
        <Table>
          <TableHeader><TableRow className="hover:bg-transparent">
            <TableHead className="h-8">Waktu tekan</TableHead>
            <TableHead className="h-8">Durasi</TableHead>
            <TableHead className="h-8">Aksi</TableHead>
            <TableHead className="hidden h-8 sm:table-cell">Keadaan sistem</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {baris.map(([lepas, lama, aksi, keadaan]) => (
              <TableRow key={lepas}>
                <TableCell className="py-1.5 tabular-nums">{jamDetik(lepas - lama)}</TableCell>
                <TableCell className="py-1.5 tabular-nums">{dtk(lama)} dtk</TableCell>
                <TableCell className="py-1.5">
                  <span className="flex items-center gap-2"><Titik warna={warnaAksi(aksi)} />{aksi}</span>
                </TableCell>
                <TableCell className="hidden py-1.5 text-muted-foreground sm:table-cell">{keadaan}</TableCell>
              </TableRow>
            ))}
            {!baris.length && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={4} className="py-6 text-center text-muted-foreground">
                  belum ada tekanan tombol dalam 2 jam terakhir
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </Panel>
  )
}
