import { useState } from "react"
import { CartesianGrid, Line, LineChart, ReferenceArea, XAxis, YAxis } from "recharts"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { aksi } from "@/lib/api"

function Kartu({ label, nilai }) {
  return (
    <div className="rounded-md border bg-card p-2.5">
      <p className="truncate text-sm font-semibold">{nilai}</p>
      <p className="text-[11px] text-muted-foreground">{label}</p>
    </div>
  )
}

function Baris({ utama, kecil, anak }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b py-2.5 last:border-0">
      <div className="min-w-0">
        <p className="truncate text-sm">{utama}</p>
        <p className="text-xs text-muted-foreground">{kecil}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">{anak}</div>
    </div>
  )
}

const konfigGrafik = {
  ear: { label: "EAR (% baseline)", color: "var(--chart-2)" },
  perclos: { label: "PERCLOS (%)", color: "var(--chart-4)" },
}

export default function Dasbor({ data }) {
  const [bt, setBt] = useState(null)
  const [wifi, setWifi] = useState(null)
  const [sandi, setSandi] = useState({})
  const [pesan, setPesan] = useState("")
  const [sibuk, setSibuk] = useState("")

  const s = data.status || {}
  const a = data.alat || {}
  // Titik grafik dikirim sebagai array ringkas [detik, ear, perclos, tingkat]
  // supaya muatan JSON tetap kecil walau berisi 7200 titik.
  const titik = (data.sampel || []).map(([detik, ear, perclos, tingkat]) => ({
    menit: +(detik / 60).toFixed(2), ear, perclos, tingkat,
  }))

  async function jalankan(nama, badan, simpan) {
    setSibuk(nama); setPesan("")
    const r = await aksi(badan)
    setSibuk(""); setPesan(r.pesan || "")
    if (simpan) simpan(r)
    return r
  }
  const pindai = () => jalankan("bt", { perintah: "bt_pindai" }, r => setBt(r.daftar || []))
  const cariWifi = () => jalankan("wifi", { perintah: "wifi_daftar" }, r => setWifi(r.daftar || []))

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="text-sm">Status alat</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {[["Kamera", a.kamera], ["Suara", a.suara], ["GPS", a.gps],
              ["Internet", a.internet], ["Kerabat", a.kerabat], ["Alarm", a.alarm]]
              .filter(([, v]) => v).map(([k, v]) => <Kartu key={k} label={k} nilai={v} />)}
          </div>
          {a.pesan && <p className="mt-3 text-sm text-amber-500">{a.pesan}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm">Kamera</CardTitle></CardHeader>
        <CardContent>
          <img src="/video" alt="video langsung" className="w-full rounded-md bg-black" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm">Kondisi sekarang</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-3 gap-3 sm:grid-cols-4">
          <Kartu label="EAR" nilai={`${(s.ear ?? 0).toFixed(0)}%`} />
          <Kartu label="PERCLOS" nilai={`${(s.perclos ?? 0).toFixed(0)}%`} />
          <Kartu label="Kedip" nilai={s.kedip ?? 0} />
          <Kartu label="Menguap" nilai={s.menguap ?? 0} />
          <Kartu label="FPS" nilai={(s.fps ?? 0).toFixed(1)} />
          <Kartu label="Alasan" nilai={s.alasan || "—"} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm">EAR &amp; PERCLOS — 2 jam terakhir</CardTitle></CardHeader>
        <CardContent>
          {titik.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground">belum ada data</p>
          ) : (
            <ChartContainer config={konfigGrafik} className="h-52 w-full">
              <LineChart data={titik} margin={{ left: 4, right: 8 }}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="menit" tickLine={false} axisLine={false} tickMargin={8}
                       unit=" mnt" minTickGap={32} />
                <YAxis domain={[0, 150]} tickLine={false} axisLine={false} width={32} unit="%" />
                {/* Periode alarm ditandai sebagai latar merah supaya terlihat
                    kapan peringatan berbunyi tanpa mengganggu garis metrik. */}
                {titik.filter(t => t.tingkat > 0).map((t, i) => (
                  <ReferenceArea key={i} x1={t.menit} x2={t.menit} fill="var(--destructive)"
                                 fillOpacity={0.35} />
                ))}
                <ChartTooltip content={<ChartTooltipContent />} />
                <Line dataKey="ear" type="monotone" stroke="var(--color-ear)" dot={false} strokeWidth={2} />
                <Line dataKey="perclos" type="monotone" stroke="var(--color-perclos)" dot={false} strokeWidth={2} />
              </LineChart>
            </ChartContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm">Riwayat kejadian</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader><TableRow>
              <TableHead>Waktu</TableHead><TableHead>Lama</TableHead>
              <TableHead>Alasan</TableHead><TableHead>Posisi</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {(data.riwayat || []).slice().reverse().map((k, i) => (
                <TableRow key={i}>
                  <TableCell>{k.jam}</TableCell>
                  <TableCell>{k.lama}</TableCell>
                  <TableCell>{k.alasan}</TableCell>
                  <TableCell>{k.tautan
                    ? <a className="underline" target="_blank" rel="noreferrer" href={k.tautan}>peta</a>
                    : "—"}</TableCell>
                </TableRow>
              ))}
              {!(data.riwayat || []).length && (
                <TableRow><TableCell colSpan={4} className="text-muted-foreground">
                  belum ada kejadian</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm">Speaker Bluetooth</CardTitle></CardHeader>
        <CardContent>
          <Button variant="secondary" onClick={pindai} disabled={sibuk === "bt"}>
            {sibuk === "bt" ? "Memindai 8 detik…" : "Pindai perangkat"}
          </Button>
          <div className="mt-3">
            {(bt || []).map(d => (
              <Baris key={d.mac} utama={d.nama}
                     kecil={`${d.mac}${d.terhubung ? " · tersambung" : d.dikenal ? " · dikenal" : ""}`}
                     anak={d.terhubung
                       ? <Button variant="secondary" size="sm"
                           onClick={() => jalankan("bt", { perintah: "bt_aksi", mac: d.mac, aksi: "putus" }).then(pindai)}>
                           Putuskan</Button>
                       : <Button size="sm"
                           onClick={() => jalankan("bt", { perintah: "bt_aksi", mac: d.mac, aksi: "sambung" }).then(pindai)}>
                           Sambungkan</Button>} />
            ))}
            {bt?.length === 0 && <p className="py-2 text-sm text-muted-foreground">tidak ada perangkat</p>}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm">WiFi</CardTitle></CardHeader>
        <CardContent>
          <Button variant="secondary" onClick={cariWifi} disabled={sibuk === "wifi"}>
            {sibuk === "wifi" ? "Mencari…" : "Cari jaringan"}
          </Button>
          <div className="mt-3">
            {(wifi || []).map(j => (
              <Baris key={j.ssid} utama={j.ssid}
                     kecil={`sinyal ${j.sinyal}%${j.aktif ? " · tersambung" : ""}${j.aman ? " · terkunci" : ""}`}
                     anak={j.aktif ? <span className="text-xs text-emerald-500">aktif</span> : <>
                       <Input type="password" placeholder="sandi" className="h-8 w-28"
                              value={sandi[j.ssid] || ""}
                              onChange={e => setSandi({ ...sandi, [j.ssid]: e.target.value })} />
                       <Button size="sm" onClick={() => jalankan("wifi",
                         { perintah: "wifi_sambung", ssid: j.ssid, sandi: sandi[j.ssid] || "" })}>
                         Sambung</Button></>} />
            ))}
            {wifi?.length === 0 && <p className="py-2 text-sm text-muted-foreground">tidak ada jaringan</p>}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm">Sistem</CardTitle></CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Button variant="secondary"
              onClick={() => confirm("Reboot sekarang?") && jalankan("sys", { perintah: "sistem", aksi: "reboot" })}>
              Reboot</Button>
            <Button variant="destructive"
              onClick={() => confirm("Matikan Raspberry Pi sekarang?") && jalankan("sys", { perintah: "sistem", aksi: "matikan" })}>
              Matikan Pi</Button>
          </div>
          {pesan && <p className="mt-3 text-sm text-amber-500">{pesan}</p>}
        </CardContent>
      </Card>
    </div>
  )
}
