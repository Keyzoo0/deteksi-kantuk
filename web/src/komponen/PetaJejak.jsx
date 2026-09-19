import { useEffect, useRef, useState } from "react"
import L from "leaflet"
import "leaflet/dist/leaflet.css"
import "./peta.css"

// Semua penyedia ubin di bawah gratis tanpa API key. CARTO Dark Matter jadi
// bawaan karena menyatu dengan dasbor gelap; OSM standar terlalu terang dan
// ramai sehingga garis jalur tenggelam di antara warna jalan.
const LAPISAN = {
  gelap: {
    nama: "Gelap",
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    atribusi: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    maks: 20,
  },
  jalan: {
    nama: "Jalan",
    url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    atribusi: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    maks: 20,
  },
  satelit: {
    nama: "Satelit",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    atribusi: "Citra &copy; Esri, Maxar, Earthstar Geographics",
    maks: 19,
  },
}

const ikonKini = L.divIcon({ className: "", html: '<div class="penanda-kini"></div>', iconSize: [18, 18], iconAnchor: [9, 9] })

function jarakKm(titik) {
  let total = 0
  for (let i = 1; i < titik.length; i++) {
    const [a, b] = [titik[i - 1], titik[i]]
    const x = ((b[1] - a[1]) * Math.PI / 180) * Math.cos(((a[0] + b[0]) / 2) * Math.PI / 180)
    const y = (b[0] - a[0]) * Math.PI / 180
    total += Math.hypot(x, y) * 6371
  }
  return total
}

export function ringkasJejak(jejak, kini) {
  const titik = kini ? [...jejak, kini] : jejak
  return { titik, km: jarakKm(titik) }
}

export default function PetaJejak({ jejak, kini }) {
  const wadah = useRef(null)
  const peta = useRef(null)
  const ubin = useRef(null)
  const garis = useRef(null)
  const penanda = useRef(null)
  const awal = useRef(null)
  const sudahFokus = useRef(false)
  const [lapisan, setLapisan] = useState("gelap")
  // Peta mengikuti posisi terbaru sampai pengguna menggeser sendiri; tanpa
  // ini peta terus ditarik balik tiap 2 detik saat orang sedang melihat-lihat.
  const [ikuti, setIkuti] = useState(true)
  const ikutiRef = useRef(true)

  // Peta dibuat sekali. Membuat ulang tiap data baru (seperti iframe dulu)
  // itulah yang membuat peta berkedip.
  useEffect(() => {
    const p = L.map(wadah.current, { zoomControl: true, attributionControl: true, preferCanvas: false })
    p.setView([-2.5, 118], 5)
    p.on("dragstart", () => { ikutiRef.current = false; setIkuti(false) })
    garis.current = {
      pendar: L.polyline([], { color: "#10b981", weight: 12, opacity: 0.18, lineCap: "round", lineJoin: "round" }).addTo(p),
      inti: L.polyline([], { color: "#34d399", weight: 4, opacity: 0.95, lineCap: "round", lineJoin: "round" }).addTo(p),
    }
    awal.current = L.circleMarker([0, 0], { radius: 5, color: "#fff", weight: 2, fillColor: "#71717a", fillOpacity: 1 })
    penanda.current = L.marker([0, 0], { icon: ikonKini, keyboard: false })
    peta.current = p
    // Tab yang disembunyikan membuat ukuran wadah 0; tanpa invalidateSize
    // ubin hanya terisi sepotong begitu tab dibuka lagi.
    const amati = new ResizeObserver(() => p.invalidateSize())
    amati.observe(wadah.current)
    return () => { amati.disconnect(); p.remove(); peta.current = null }
  }, [])

  useEffect(() => {
    const p = peta.current
    if (!p) return
    const l = LAPISAN[lapisan]
    ubin.current?.remove()
    ubin.current = L.tileLayer(l.url, { attribution: l.atribusi, maxZoom: l.maks, subdomains: "abcd", detectRetina: false }).addTo(p)
    ubin.current.bringToBack()
  }, [lapisan])

  useEffect(() => {
    const p = peta.current
    if (!p) return
    const { titik } = ringkasJejak(jejak, kini)
    garis.current.pendar.setLatLngs(titik)
    garis.current.inti.setLatLngs(titik)
    if (titik.length > 1) awal.current.setLatLng(titik[0]).addTo(p)
    else awal.current.remove()
    if (!titik.length) { penanda.current.remove(); return }
    const akhir = titik[titik.length - 1]
    penanda.current.setLatLng(akhir).addTo(p)
    if (!sudahFokus.current) {
      sudahFokus.current = true
      if (titik.length > 1) p.fitBounds(L.latLngBounds(titik), { padding: [40, 40], maxZoom: 17 })
      else p.setView(akhir, 17)
    } else if (ikutiRef.current) {
      p.panTo(akhir, { animate: true, duration: 0.8 })
    }
  }, [jejak, kini])

  const lihatSemua = () => {
    const { titik } = ringkasJejak(jejak, kini)
    if (!peta.current || !titik.length) return
    ikutiRef.current = false
    setIkuti(false)
    if (titik.length > 1) peta.current.fitBounds(L.latLngBounds(titik), { padding: [40, 40], maxZoom: 17 })
    else peta.current.setView(titik[0], 17)
  }
  const ikutiPosisi = () => {
    ikutiRef.current = true
    setIkuti(true)
    const { titik } = ringkasJejak(jejak, kini)
    if (peta.current && titik.length) peta.current.setView(titik[titik.length - 1], Math.max(peta.current.getZoom(), 16))
  }

  const tombol = "rounded-md px-2.5 py-1 text-xs font-medium transition-colors"
  return (
    <div className="relative isolate overflow-hidden rounded-lg border">
      <div ref={wadah} className="peta-jejak h-80 w-full sm:h-[420px]" />
      <div className="pointer-events-none absolute inset-x-2 top-2 z-[1000] flex flex-wrap justify-end gap-2">
        <div className="pointer-events-auto flex gap-0.5 rounded-lg border border-white/10 bg-zinc-900/85 p-0.5 shadow-lg backdrop-blur">
          {Object.entries(LAPISAN).map(([k, l]) => (
            <button key={k} type="button" onClick={() => setLapisan(k)}
                    className={`${tombol} ${lapisan === k ? "bg-white/15 text-white" : "text-zinc-400 hover:text-white"}`}>
              {l.nama}
            </button>
          ))}
        </div>
        <div className="pointer-events-auto flex gap-0.5 rounded-lg border border-white/10 bg-zinc-900/85 p-0.5 shadow-lg backdrop-blur">
          <button type="button" onClick={ikutiPosisi}
                  className={`${tombol} ${ikuti ? "bg-emerald-500/20 text-emerald-300" : "text-zinc-400 hover:text-white"}`}>
            Ikuti
          </button>
          <button type="button" onClick={lihatSemua} className={`${tombol} text-zinc-400 hover:text-white`}>
            Seluruh jalur
          </button>
        </div>
      </div>
    </div>
  )
}
