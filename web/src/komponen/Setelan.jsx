import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Baris, Kartu, Panel } from "@/komponen/bagian"
import UbahInfo from "@/komponen/UbahInfo"
import { aksi } from "@/lib/api"

export default function Setelan({ info, setInfo, setVersiLogo }) {
  const [bt, setBt] = useState(null)
  const [wifi, setWifi] = useState(null)
  const [sandi, setSandi] = useState({})
  const [sistem, setSistem] = useState(null)
  const [pesan, setPesan] = useState("")
  const [sibuk, setSibuk] = useState("")

  async function jalankan(nama, badan, simpan) {
    setSibuk(nama); setPesan("")
    const r = await aksi(badan)
    setSibuk(""); setPesan(r.pesan || "")
    simpan?.(r)
    return r
  }
  const pindai = () => jalankan("bt", { perintah: "bt_pindai" }, r => setBt(r.daftar || []))
  const cariWifi = () => jalankan("wifi", { perintah: "wifi_daftar" }, r => setWifi(r.daftar || []))
  const muatSistem = () => jalankan("sys", { perintah: "info" }, r => setSistem(r.info || {}))

  return (
    <div className="grid gap-4 xl:grid-cols-12">
      <Panel judul="Speaker Bluetooth" kelas="xl:col-span-4"
        aksi={<Button size="sm" variant="secondary" onClick={pindai} disabled={sibuk === "bt"}>
          {sibuk === "bt" ? "Memindai…" : "Pindai"}</Button>}>
        {bt === null
          ? <p className="py-6 text-center text-sm text-muted-foreground">
              Tekan Pindai untuk mencari perangkat di sekitar.</p>
          : bt.length === 0
            ? <p className="py-6 text-center text-sm text-muted-foreground">tidak ada perangkat</p>
            : bt.map(d => (
                <Baris key={d.mac} utama={d.nama}
                  kecil={`${d.mac}${d.terhubung ? " · tersambung" : d.dikenal ? " · dikenal" : ""}`}
                  anak={d.terhubung
                    ? <Button size="sm" variant="secondary" disabled={sibuk === "bt"}
                        onClick={() => jalankan("bt", { perintah: "bt_aksi", mac: d.mac, aksi: "putus" }).then(pindai)}>
                        Putuskan</Button>
                    : <Button size="sm" disabled={sibuk === "bt"}
                        onClick={() => jalankan("bt", { perintah: "bt_aksi", mac: d.mac, aksi: "sambung" }).then(pindai)}>
                        Sambungkan</Button>} />
              ))}
      </Panel>

      <Panel judul="WiFi" kelas="xl:col-span-4"
        aksi={<Button size="sm" variant="secondary" onClick={cariWifi} disabled={sibuk === "wifi"}>
          {sibuk === "wifi" ? "Mencari…" : "Cari jaringan"}</Button>}>
        {wifi === null
          ? <p className="py-6 text-center text-sm text-muted-foreground">
              Tekan Cari jaringan untuk melihat WiFi di sekitar.</p>
          : wifi.length === 0
            ? <p className="py-6 text-center text-sm text-muted-foreground">tidak ada jaringan</p>
            : <div className="max-h-72 overflow-y-auto pr-1">
                {wifi.map(j => (
                  <Baris key={j.ssid} utama={j.ssid}
                    kecil={`sinyal ${j.sinyal}%${j.aktif ? " · tersambung" : ""}${j.aman ? " · terkunci" : ""}`}
                    anak={j.aktif
                      ? <span className="text-xs text-emerald-500">aktif</span>
                      : <>
                          <Input type="password" placeholder="sandi" className="h-8 w-24"
                            value={sandi[j.ssid] || ""}
                            onChange={e => setSandi({ ...sandi, [j.ssid]: e.target.value })} />
                          <Button size="sm" disabled={sibuk === "wifi"}
                            onClick={() => jalankan("wifi", { perintah: "wifi_sambung",
                              ssid: j.ssid, sandi: sandi[j.ssid] || "" })}>Sambung</Button>
                        </>} />
                ))}
              </div>}
      </Panel>

      <Panel judul="Sistem" kelas="xl:col-span-4"
        aksi={<Button size="sm" variant="secondary" onClick={muatSistem} disabled={sibuk === "sys"}>
          Segarkan</Button>}>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {Object.entries(sistem || {}).map(([k, v]) => <Kartu key={k} label={k} nilai={v} />)}
          {!sistem && <p className="col-span-full py-2 text-sm text-muted-foreground">
            Tekan Segarkan untuk membaca suhu, alamat, dan lama nyala.</p>}
        </div>
        <div className="mt-4 flex gap-2">
          <Button variant="secondary" size="sm"
            onClick={() => confirm("Reboot sekarang?") && jalankan("sys", { perintah: "sistem", aksi: "reboot" })}>
            Reboot</Button>
          <Button variant="destructive" size="sm"
            onClick={() => confirm("Matikan Raspberry Pi sekarang?") && jalankan("sys", { perintah: "sistem", aksi: "matikan" })}>
            Matikan Pi</Button>
        </div>
        {pesan && <p className="mt-3 text-sm text-amber-500">{pesan}</p>}
      </Panel>

      <UbahInfo info={info} setInfo={setInfo} setVersiLogo={setVersiLogo} />
    </div>
  )
}
