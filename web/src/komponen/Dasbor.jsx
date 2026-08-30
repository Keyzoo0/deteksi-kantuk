import { CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { Separator } from "@/components/ui/separator"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Kartu, Panel } from "@/komponen/bagian"

// Warna garis ditulis harfiah, bukan token tema: token bawaan shadcn untuk
// grafik semuanya abu-abu, sedangkan dua metrik ini harus bisa dibedakan
// sekilas.
const konfigGrafik = {
  ear: { label: "EAR (% baseline)", color: "oklch(0.72 0.17 145)" },
  perclos: { label: "PERCLOS (%)", color: "oklch(0.78 0.14 75)" },
}

function Peringatan({ teks }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-amber-500/25 bg-amber-500/10 px-3 py-2">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="2" strokeLinecap="round" className="shrink-0 text-amber-400">
        <circle cx="12" cy="12" r="9" /><path d="M12 8v5" /><path d="M12 16h.01" />
      </svg>
      <p className="text-sm text-amber-200/90">{teks}</p>
    </div>
  )
}

export default function Dasbor({ data }) {
  const s = data.status || {}
  const a = data.alat || {}
  // Titik dikirim ringkas [detik, ear, perclos, tingkat] supaya muatan JSON
  // tetap kecil walau berisi 7200 titik.
  const titik = (data.sampel || []).map(([detik, ear, perclos, tingkat]) => ({
    menit: +(detik / 60).toFixed(2), ear, perclos, tingkat,
  }))
  const riwayat = (data.riwayat || []).slice().reverse()

  return (
    <div className="grid gap-4 xl:grid-cols-12">
      <Panel judul="Kamera" kelas="xl:col-span-3"
             aksi={<span className="text-xs text-muted-foreground">
               {s.fps ? `${s.fps.toFixed(1)} fps` : "siaga"}</span>}>
        {/* Tanpa rasio yang dipaksakan: frame kamera berputar 90 derajat jadi
            potret, dan memaksanya ke kotak lanskap hanya menghasilkan pita
            hitam lebar di kiri-kanan. */}
        <img src="/video" alt="video langsung" className="w-full rounded-md border bg-black" />
      </Panel>

      <Panel judul="Status alat" kelas="xl:col-span-5">
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          {[["Kamera", a.kamera], ["Suara", a.suara], ["GPS", a.gps],
            ["Internet", a.internet], ["Kerabat", a.kerabat], ["Alarm", a.alarm]]
            .filter(([, v]) => v).map(([k, v]) => <Kartu key={k} label={k} nilai={v} />)}
        </div>
        {a.pesan && <div className="mt-3"><Peringatan teks={a.pesan} /></div>}
        <Separator className="my-4" />
        <p className="mb-2.5 text-sm font-semibold">Kondisi sekarang</p>
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          <Kartu label="EAR (% baseline)" nilai={`${(s.ear ?? 0).toFixed(0)}%`} />
          <Kartu label="PERCLOS" nilai={`${(s.perclos ?? 0).toFixed(0)}%`} />
          <Kartu label="Kedip" nilai={s.kedip ?? 0} />
          <Kartu label="Menguap" nilai={s.menguap ?? 0} />
          <Kartu label="Tingkat alarm" nilai={a.alarm ?? "—"} />
          <Kartu label="Alasan" nilai={s.alasan || "—"} />
        </div>
      </Panel>

      <Panel judul="Riwayat kejadian" kelas="xl:col-span-4"

             aksi={<span className="text-xs text-muted-foreground">
               {riwayat.length} kejadian</span>}>
        <div className="max-h-52 overflow-y-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              <TableHead className="h-8">Waktu</TableHead><TableHead className="h-8">Lama</TableHead>
              <TableHead className="h-8">Alasan</TableHead><TableHead className="h-8">Peta</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {riwayat.map((k, i) => (
                <TableRow key={i}>
                  <TableCell className="py-1.5">{k.jam}</TableCell>
                  <TableCell className="py-1.5">{k.lama}</TableCell>
                  <TableCell className="py-1.5">{k.alasan}</TableCell>
                  <TableCell className="py-1.5">{k.tautan
                    ? <a className="underline" target="_blank" rel="noreferrer" href={k.tautan}>buka</a>
                    : "—"}</TableCell>
                </TableRow>
              ))}
              {!riwayat.length && (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={4} className="py-6 text-center text-muted-foreground">
                    belum ada kejadian</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </Panel>
      <Panel judul="EAR & PERCLOS — 2 jam terakhir" kelas="xl:col-span-12"
        aksi={<div className="flex gap-3 text-xs text-muted-foreground">
          {[["EAR", konfigGrafik.ear.color], ["PERCLOS", konfigGrafik.perclos.color]].map(([n, c]) => (
            <span key={n} className="flex items-center gap-1.5">
              <span className="h-0.5 w-2.5 rounded-full" style={{ background: c }} />{n}</span>
          ))}
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-xs bg-destructive/60" />alarm</span>
        </div>}>
        {titik.length === 0 ? (
          <div className="flex h-44 items-center justify-center rounded-md border bg-background
                          text-sm text-muted-foreground">
            belum ada data — grafik terisi setelah monitoring berjalan
          </div>
        ) : (
          <ChartContainer config={konfigGrafik} className="h-44 w-full">
            <LineChart data={titik} margin={{ left: 0, right: 8, top: 4 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="menit" tickLine={false} axisLine={false} tickMargin={8}
                     unit=" mnt" minTickGap={40} />
              <YAxis domain={[0, 150]} tickLine={false} axisLine={false} width={34} unit="%" />
              {/* Garis tipis menandai saat alarm berbunyi, tanpa menutupi metrik. */}
              {titik.filter(t => t.tingkat > 0).map((t, i) => (
                <ReferenceLine key={i} x={t.menit} stroke="var(--destructive)" strokeOpacity={0.45} />
              ))}
              <ChartTooltip content={<ChartTooltipContent />} />
              <Line dataKey="ear" type="monotone" stroke="var(--color-ear)" dot={false} strokeWidth={2} />
              <Line dataKey="perclos" type="monotone" stroke="var(--color-perclos)" dot={false} strokeWidth={2} />
            </LineChart>
          </ChartContainer>
        )}
      </Panel>

    </div>
  )
}
