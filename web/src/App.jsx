import { useEffect, useState } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import Dasbor from "@/komponen/Dasbor"
import Info from "@/komponen/Info"
import { ambil } from "@/lib/api"

export default function App() {
  const [data, setData] = useState({ status: {}, alat: {}, sampel: [], riwayat: [] })
  const [info, setInfo] = useState(null)

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
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-3">
          <img src="/logo" alt="logo" className="size-9 shrink-0 object-contain" />
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-sm font-semibold leading-tight">
              {info?.judul || "Monitor Kantuk"}
            </h1>
            <p className="truncate text-xs text-muted-foreground">
              {[info?.departemen, info?.jurusan].filter(Boolean).join(" · ") || "Raspberry Pi"}
            </p>
          </div>
          <Badge variant={rupa} className="shrink-0">{label}</Badge>
        </div>
      </header>

      <Tabs defaultValue="dasbor" className="mx-auto max-w-4xl px-4 py-4">
        <TabsList className="mb-4">
          <TabsTrigger value="dasbor">Dashboard</TabsTrigger>
          <TabsTrigger value="info">Info</TabsTrigger>
        </TabsList>
        <TabsContent value="dasbor"><Dasbor data={data} /></TabsContent>
        <TabsContent value="info"><Info info={info} setInfo={setInfo} /></TabsContent>
      </Tabs>
    </div>
  )
}
