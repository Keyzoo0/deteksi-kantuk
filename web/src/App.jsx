import { useEffect, useState } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import Dasbor from "@/komponen/Dasbor"
import Setelan from "@/komponen/Setelan"
import Info from "@/komponen/Info"
import { ambil } from "@/lib/api"

// Tema disimpan di peramban masing-masing (bukan di alat): satu Pi bisa
// dibuka dari beberapa HP, dan tiap orang punya selera sendiri.
function bacaTema() {
  try {
    const t = localStorage.getItem("tema")
    if (t === "terang" || t === "gelap") return t
    return matchMedia("(prefers-color-scheme: light)").matches ? "terang" : "gelap"
  } catch { return "gelap" }
}

function TombolTema({ tema, setTema }) {
  const gelap = tema === "gelap"
  return (
    <button type="button" onClick={() => setTema(gelap ? "terang" : "gelap")}
            title={gelap ? "Ganti ke tampilan terang" : "Ganti ke tampilan gelap"}
            aria-label={gelap ? "Ganti ke tampilan terang" : "Ganti ke tampilan gelap"}
            className="flex size-8 shrink-0 items-center justify-center rounded-md border
                       text-muted-foreground transition-colors hover:bg-accent
                       hover:text-foreground">
      {gelap ? (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="2" strokeLinecap="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  )
}

export default function App() {
  const [data, setData] = useState({ status: {}, alat: {}, sampel: [], riwayat: [] })
  const [info, setInfo] = useState(null)
  // Berubah tiap halaman dimuat dan tiap logo diganti; tanpa ini peramban HP
  // bisa terus menampilkan logo lama dari cache-nya sendiri.
  const [versiLogo, setVersiLogo] = useState(() => Date.now())
  const [tema, setTema] = useState(bacaTema)

  useEffect(() => {
    document.documentElement.classList.toggle("dark", tema === "gelap")
    // Warna bilah status peramban HP ikut tema, kalau tidak bilahnya gelap
    // sendirian di atas halaman terang.
    document.querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", tema === "gelap" ? "#0a0a0b" : "#ffffff")
    try { localStorage.setItem("tema", tema) } catch { /* mode privat */ }
  }, [tema])

  // Satu sumber data untuk seluruh halaman: dashboard menampilkannya, dan
  // header memakai judul dari tab Info.
  useEffect(() => {
    const tarik = () => ambil("/data").then(setData).catch(() => {})
    tarik()
    const jam = setInterval(tarik, 2000)
    return () => clearInterval(jam)
  }, [])
  useEffect(() => { ambil("/info").then(setInfo).catch(() => setInfo({})) }, [])

  const s = data.status || {}
  // Saat wajah hilang penilai tetap berlevel AMAN (tak ada bukti kantuk),
  // jadi lencana memakai status_deteksi supaya tidak tertulis AMAN palsu.
  const deteksi = s.status_deteksi || s.level
  const label = deteksi === "TANPA_WAJAH" ? "TANPA WAJAH"
    : deteksi || { siaga: "SIAGA", kalibrasi: "KALIBRASI" }[s.keadaan] || "—"
  const rupa = deteksi === "KANTUK" ? "destructive"
    : deteksi === "AMAN" ? "default" : "secondary"

  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="sticky top-0 z-10 border-b bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-[1440px] items-center gap-3 px-4 py-2.5 sm:px-7">
          <img src={`/logo?v=${versiLogo}`} alt="logo" className="size-9 shrink-0 object-contain" />
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-sm font-semibold leading-tight">
              {info?.judul || "Monitor Kantuk"}
            </h1>
            <p className="truncate text-xs text-muted-foreground">
              {[info?.departemen, info?.jurusan].filter(Boolean).join(" · ") || "Raspberry Pi"}
            </p>
          </div>
          <span className="hidden shrink-0 items-center gap-1.5 text-xs text-muted-foreground sm:flex">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" strokeWidth="2"
                 strokeLinecap="round" className={s.keadaan ? "stroke-emerald-500" : "stroke-muted-foreground"}>
              <path d="M5 12.55a11 11 0 0 1 14.08 0" /><path d="M1.42 9a16 16 0 0 1 21.16 0" />
              <path d="M8.53 16.11a6 6 0 0 1 6.95 0" /><circle cx="12" cy="20" r="1" />
            </svg>
            {location.host}
          </span>
          <Badge variant={rupa}
                 className={`shrink-0 ${rupa === "destructive"
                   ? "text-red-800 dark:text-red-300" : ""}`}>{label}</Badge>
          <TombolTema tema={tema} setTema={setTema} />
        </div>
      </header>

      <Tabs defaultValue="dasbor" className="mx-auto max-w-[1440px] px-4 py-4 sm:px-7">
        <TabsList className="mb-4">
          <TabsTrigger value="dasbor">Dashboard</TabsTrigger>
          <TabsTrigger value="setelan">Settings</TabsTrigger>
          <TabsTrigger value="info">Info</TabsTrigger>
        </TabsList>
        <TabsContent value="dasbor"><Dasbor data={data} /></TabsContent>
        <TabsContent value="setelan">
          <Setelan info={info} setInfo={setInfo} setVersiLogo={setVersiLogo} />
        </TabsContent>
        <TabsContent value="info"><Info info={info} versiLogo={versiLogo} /></TabsContent>
      </Tabs>
    </div>
  )
}
