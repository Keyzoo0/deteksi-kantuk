import { useEffect, useState } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import Dasbor from "@/komponen/Dasbor"
import Setelan from "@/komponen/Setelan"
import Info from "@/komponen/Info"
import { ambil } from "@/lib/api"

export default function App() {
  const [data, setData] = useState({ status: {}, alat: {}, sampel: [], riwayat: [] })
  const [info, setInfo] = useState(null)
  // Berubah tiap halaman dimuat dan tiap logo diganti; tanpa ini peramban HP
  // bisa terus menampilkan logo lama dari cache-nya sendiri.
  const [versiLogo, setVersiLogo] = useState(() => Date.now())

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
  const label = s.level || { siaga: "SIAGA", kalibrasi: "KALIBRASI" }[s.keadaan] || "—"
  const rupa = s.level === "KANTUK" ? "destructive" : s.level ? "default" : "secondary"

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
          <Badge variant={rupa} className="shrink-0">{label}</Badge>
        </div>
      </header>

      <Tabs defaultValue="dasbor" className="mx-auto max-w-[1440px] px-4 py-4 sm:px-7">
        <TabsList className="mb-4">
          <TabsTrigger value="dasbor">Dashboard</TabsTrigger>
          <TabsTrigger value="setelan">Settings</TabsTrigger>
          <TabsTrigger value="info">Info</TabsTrigger>
        </TabsList>
        <TabsContent value="dasbor"><Dasbor data={data} /></TabsContent>
        <TabsContent value="setelan"><Setelan /></TabsContent>
        <TabsContent value="info"><Info info={info} setInfo={setInfo} setVersiLogo={setVersiLogo} /></TabsContent>
      </Tabs>
    </div>
  )
}
