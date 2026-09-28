import { CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { Separator } from "@/components/ui/separator"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Kartu, Panel } from "@/komponen/bagian"

// Warna garis punya token sendiri (lihat index.css): token chart-N bawaan
// shadcn semuanya abu-abu, sedangkan dua metrik ini harus bisa dibedakan
// sekilas -- dan nilainya berbeda antara tema terang dan gelap supaya
// sama-sama terbaca.
const konfigGrafik = {
  ear: { label: "EAR (% baseline)", color: "var(--garis-ear)" },
  perclos: { label: "PERCLOS (%)", color: "var(--garis-perclos)" },
}

// Sebelum kalibrasi selesai (atau sebelum sistem dinyalakan) belum ada
// baseline untuk ditampilkan -- kartu tetap dirender dengan "—" alih-alih
// panelnya disembunyikan, supaya halaman tidak terlihat kosong/rusak.
function PanelKalibrasi({ s }) {
  const k = s.kalibrasi
  const selesai = s.keadaan === "monitor" && k
  // Timer kalibrasi baru jalan setelah wajah pertama terlihat, jadi "menunggu
  // wajah" dan "mengumpulkan data" dibedakan -- kalau disamakan, panel seolah
  // menghitung mundur padahal belum ada satu frame pun yang terkumpul.
  const mengumpulkan = s.keadaan === "kalibrasi" && s.mulai
  const menunggu = s.keadaan === "kalibrasi" && !s.mulai
  const status = selesai ? "Selesai"
    : mengumpulkan ? "Mengumpulkan data"
    : menunggu ? "Menunggu wajah" : "Belum dimulai"

  return (
    <Panel judul="Kalibrasi" kelas="xl:col-span-6">
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        <Kartu label="Status" nilai={status} />
        <Kartu label="Sisa waktu"
               nilai={mengumpulkan ? `${(s.sisa ?? 0).toFixed(1)} detik` : "—"} />
        <Kartu label="Sampel Kalibrasi"
               nilai={selesai ? `${k.sampel} frame`
                      : mengumpulkan || menunggu ? `${s.sampel ?? 0} frame (sementara)` : "—"} />
        <Kartu label="EAR Baseline" nilai={selesai ? k.ear_baseline.toFixed(3) : "—"} />
        <Kartu label="EAR Threshold"
               nilai={selesai
                      ? `${k.ear_threshold.toFixed(3)} / ${k.ear_threshold_persen.toFixed(0)}%`
                      : "—"} />
        <Kartu label="MAR Baseline" nilai={selesai ? k.mar_baseline.toFixed(3) : "—"} />
        <Kartu label="MAR Threshold" nilai={selesai ? k.mar_threshold.toFixed(3) : "—"} />
      </div>
    </Panel>
  )
}

// Status deteksi = penilaian frame saat ini; tingkat alarm = tangga eskalasi
// yang baru padam setelah tombol ditekan. Keduanya sering berbeda (frame
// sudah AMAN, alarm masih tingkat 2), jadi ditampilkan terpisah dan berlabel.
const RUPA_DETEKSI = {
  AMAN: ["AMAN", "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"],
  KANTUK: ["KANTUK", "border-destructive/40 bg-destructive/15 text-red-800 dark:text-red-300"],
  TANPA_WAJAH: ["Wajah tidak terdeteksi",
                "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300"],
}
const TEKS_ALARM = ["Tenang", "Tingkat 1 · peringatan suara",
                    "Tingkat 2 · alarm menerus", "Tingkat 3 · kerabat dikabari"]
const RUPA_ALARM = ["border-border bg-muted/40 text-foreground dark:bg-background",
                    "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
                    "border-destructive/40 bg-destructive/15 text-red-800 dark:text-red-300",
                    "border-destructive/60 bg-destructive/25 text-red-900 dark:text-red-200"]

function Lencana({ label, nilai, ket, rupa }) {
  return (
    <div className={`rounded-md border px-3 py-2 ${rupa}`}>
      {/* Tanpa opacity: teks 11px di atas latar berwarna jadi terlalu tipis
          untuk dibaca di bawah matahari (lihat tools/cek_kontras_web.mjs). */}
      <p className="text-[11px] leading-tight">{label}</p>
      <p className="text-base font-semibold leading-snug">{nilai}</p>
      <p className="text-[11px] leading-tight">{ket}</p>
    </div>
  )
}

// Rincian per-frame; cuma terisi selagi keadaan "monitor" (mata/mulut belum
// pernah diukur sebelum baseline ada).
function PanelDeteksi({ s }) {
  const aktif = s.keadaan === "monitor"
  const tanpaWajah = aktif && !s.wajah
  // Mata dan mulut hanya terukur selagi wajah terlihat; tanpa wajah nilainya
  // tertinggal di angka lama, jadi ditampilkan "—" alih-alih berbohong.
  const ukur = (v) => (aktif && s.wajah ? v : "—")
  const [teksDeteksi, rupaDeteksi] = aktif
    ? RUPA_DETEKSI[s.status_deteksi] || RUPA_DETEKSI.AMAN
    : ["—", "border-border bg-muted/40 text-muted-foreground dark:bg-background"]
  const tingkat = Math.min(3, Math.max(0, s.tingkat ?? 0))

  return (
    <Panel judul="Detail Deteksi" kelas="xl:col-span-6">
      <div className="mb-2.5 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        <Lencana label="Status deteksi" nilai={teksDeteksi} rupa={rupaDeteksi}
                 ket="penilaian frame saat ini" />
        <Lencana label="Tingkat alarm" nilai={aktif ? TEKS_ALARM[tingkat] : "—"}
                 rupa={aktif ? RUPA_ALARM[tingkat]
                             : "border-border bg-muted/40 text-muted-foreground dark:bg-background"}
                 ket="eskalasi; padam setelah tombol ditekan" />
      </div>
      {tanpaWajah && (
        <div className="mb-2.5">
          <Peringatan teks="Wajah tidak terdeteksi — data wajah tidak tersedia. Nilai mata dan mulut tidak diukur; status ini bukan berarti AMAN." />
        </div>
      )}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <Kartu label="Wajah"
               nilai={aktif ? (s.wajah ? "Terdeteksi" : "Tidak terdeteksi") : "—"} />
        <Kartu label="EAR Raw" nilai={ukur((s.ear_raw ?? 0).toFixed(3))} />
        <Kartu label="Mata" nilai={ukur(s.mata_tertutup ? "Tertutup" : "Terbuka")} />
        <Kartu label="Durasi Terpejam"
               nilai={ukur(`${(s.durasi_tertutup ?? 0).toFixed(1)} detik`)} />
        <Kartu label="MAR Raw" nilai={ukur((s.mar_raw ?? 0).toFixed(3))} />
        <Kartu label="Mulut" nilai={ukur(s.sedang_menguap ? "Menguap" : "Normal")} />
        <Kartu label="Durasi Menguap"
               nilai={ukur(`${(s.durasi_menguap ?? 0).toFixed(1)} detik`)} />
        <Kartu label="PERCLOS" nilai={aktif ? (s.perclos_matang ? "Siap" : "Belum") : "—"} />
      </div>
    </Panel>
  )
}

function Peringatan({ teks }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-amber-500/25 bg-amber-500/10 px-3 py-2">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="2" strokeLinecap="round"
           className="shrink-0 text-amber-600 dark:text-amber-400">
        <circle cx="12" cy="12" r="9" /><path d="M12 8v5" /><path d="M12 16h.01" />
      </svg>
      <p className="text-sm text-amber-800 dark:text-amber-200/90">{teks}</p>
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
          <Kartu label="EAR (% baseline)"
                 nilai={s.ear == null ? "—" : `${s.ear.toFixed(0)}%`} />
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
              <TableHead className="h-8">Waktu</TableHead><TableHead className="h-8">Durasi</TableHead>
              <TableHead className="h-8">Kondisi</TableHead><TableHead className="h-8">Peta</TableHead>
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

      <PanelKalibrasi s={s} />
      <PanelDeteksi s={s} />

      <Panel judul="EAR & PERCLOS — 2 jam terakhir" kelas="xl:col-span-12"
        aksi={<div className="flex items-center gap-3 text-xs text-muted-foreground">
          {[["EAR", konfigGrafik.ear.color], ["PERCLOS", konfigGrafik.perclos.color]].map(([n, c]) => (
            <span key={n} className="flex items-center gap-1.5">
              <span className="h-0.5 w-2.5 rounded-full" style={{ background: c }} />{n}</span>
          ))}
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-xs bg-destructive/60" />alarm</span>
          {/* CSV grafik: satu baris per detik, semua kolom (lihat
              KeadaanBersama.ekspor_csv). CSV kejadian: tiap kedip / mata
              terpejam / menguap dengan waktu dan durasinya -- kedipan terlalu
              singkat untuk tertangkap sampel 1 Hz. */}
          <a href="/ekspor.csv" download
             className="underline decoration-dotted hover:text-foreground">
            CSV grafik
          </a>
          <a href="/ekspor-kejadian.csv" download
             className="underline decoration-dotted hover:text-foreground">
            CSV kejadian
          </a>
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
              {/* Lebar 34 memotong "150%" jadi "50%" -- angka teratas skala. */}
              <YAxis domain={[0, 150]} tickLine={false} axisLine={false} width={46} unit="%" />
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

      {/* 0,0 dipakai backend sebagai "belum ada posisi" (titik nol ada di
          tengah laut, jadi aman dipakai sebagai penanda kosong) -- panel
          ini baru muncul begitu GPS benar-benar sempat fix. */}
      {!!(a.lat || a.lon) && (
        <Panel judul="Lokasi" kelas="xl:col-span-12">
          <div className="overflow-hidden rounded-md border">
            <iframe
              title="lokasi terakhir"
              className="h-64 w-full"
              src={`https://www.openstreetmap.org/export/embed.html?bbox=${a.lon - 0.004}%2C${a.lat - 0.003}%2C${a.lon + 0.004}%2C${a.lat + 0.003}&layer=mapnik&marker=${a.lat}%2C${a.lon}`}
            />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            {a.lat.toFixed(6)}, {a.lon.toFixed(6)} —{" "}
            <a className="underline" target="_blank" rel="noreferrer" href={a.tautan}>
              buka di Google Maps
            </a>
          </p>
        </Panel>
      )}

    </div>
  )
}
