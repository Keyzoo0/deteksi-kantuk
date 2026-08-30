import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Panel } from "@/komponen/bagian"
import { aksi, ambil } from "@/lib/api"

// Pengubahan lembar sampul tinggal di tab Settings; tab Info hanya menampilkan.
// Karena itu tidak ada tombol Edit di sini -- semua isian langsung dapat
// diketik, dan yang tersisa hanya Simpan.
const BIDANG = [
  ["judul", "Judul Dokumen", 4],
  ["jenis_dokumen", "Jenis Dokumen"],
  ["nomor_revisi", "Nomor Revisi"],
  ["jumlah_halaman", "Jumlah Halaman"],
  ["tanggal_terbit", "Tanggal Penerbitan"],
  ["nomor_dokumen", "Nomor Dokumen", 2],
  ["nama_file", "Nama File", 2],
  ["unit_penerbit", "Unit Penerbit", 2],
  ["universitas", "Universitas / Fakultas", 2],
  ["departemen", "Departemen", 2],
  ["jurusan", "Jurusan", 2],
  ["alamat", "Alamat", 2],
  ["kontak", "Kontak", 2],
]
const RENTANG = { 2: "sm:col-span-2", 3: "sm:col-span-3", 4: "sm:col-span-4" }

function Isian({ label, nilai, onChange, lebar }) {
  return (
    <div className={RENTANG[lebar]}>
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Input className="mt-1" value={nilai || ""} onChange={e => onChange(e.target.value)} />
    </div>
  )
}

export default function UbahInfo({ info, setInfo, setVersiLogo }) {
  const [draf, setDraf] = useState({})
  const [pesan, setPesan] = useState("")
  const [versi, setVersi] = useState(0)
  const berkas = useRef(null)

  useEffect(() => { setDraf(structuredClone(info || {})) }, [info])
  if (!info) return null

  const set = (kunci, nilai) => setDraf({ ...draf, [kunci]: nilai })
  const setDalam = (daftar, i, kunci, nilai) => {
    const salinan = structuredClone(draf)
    salinan[daftar][i][kunci] = nilai
    setDraf(salinan)
  }
  const tambah = (daftar, isi) => setDraf({ ...draf, [daftar]: [...(draf[daftar] || []), isi] })
  const hapus = (daftar, i) =>
    setDraf({ ...draf, [daftar]: draf[daftar].filter((_, n) => n !== i) })

  async function simpan() {
    const r = await aksi({ perintah: "simpan_info", info: draf })
    setPesan(r.pesan || (r.ok ? "tersimpan" : "gagal menyimpan"))
    if (r.ok) ambil("/info").then(setInfo)
  }

  async function gantiLogo(e) {
    const f = e.target.files?.[0]
    if (!f) return
    if (f.size > 2 * 1024 * 1024) return setPesan("berkas lebih dari 2 MB")
    const pembaca = new FileReader()
    pembaca.onload = async () => {
      const r = await aksi({ perintah: "simpan_logo", data: pembaca.result })
      setPesan(r.pesan || (r.ok ? "logo diganti" : "gagal mengganti logo"))
      if (r.ok) { const v = Date.now(); setVersi(v); setVersiLogo?.(v) }
    }
    pembaca.readAsDataURL(f)
  }

  return (
    <Panel judul="Lembar sampul dokumen" kelas="xl:col-span-12"
           aksi={<Button size="sm" onClick={simpan}>Simpan</Button>}>
      <div className="flex items-center gap-4">
        <img src={`/logo?v=${versi}`} alt="logo universitas"
             className="size-16 shrink-0 rounded-md border bg-background object-contain p-1.5" />
        <div>
          <p className="text-sm font-medium">Logo universitas</p>
          <p className="mb-2 text-xs text-muted-foreground">PNG/JPG, maksimal 2 MB.</p>
          <input ref={berkas} type="file" accept="image/*" className="hidden" onChange={gantiLogo} />
          <Button size="sm" variant="secondary" onClick={() => berkas.current.click()}>
            Ganti logo</Button>
        </div>
      </div>

      <Separator className="my-4" />

      <div className="grid gap-3 sm:grid-cols-4">
        {BIDANG.map(([kunci, label, lebar]) => (
          <Isian key={kunci} label={label} lebar={lebar}
                 nilai={draf[kunci]} onChange={v => set(kunci, v)} />
        ))}
      </div>

      <Separator className="my-4" />

      <div className="grid gap-4 lg:grid-cols-2">
        {[["mahasiswa", "Data pengusul", { nama: "", nim: "" }, ["nama", "Nama"], ["nim", "NIM"]],
          ["pembimbing", "Pembimbing", { peran: "", nama: "", nip: "" }, ["nama", "Nama"], ["nip", "NIP"]]]
          .map(([daftar, judul, kosong, ...kolom]) => (
          <div key={daftar}>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-sm font-semibold">{judul}</p>
              <Button size="sm" variant="secondary" onClick={() => tambah(daftar, kosong)}>
                + Tambah</Button>
            </div>
            <div className="grid gap-3">
              {(draf[daftar] || []).map((butir, i) => (
                <div key={i} className="grid gap-3 rounded-md border p-3 sm:grid-cols-2">
                  <div className="flex items-center justify-between gap-2 sm:col-span-2">
                    {daftar === "pembimbing"
                      ? <div className="min-w-0 flex-1">
                          <Isian label="Peran" nilai={butir.peran}
                                 onChange={v => setDalam(daftar, i, "peran", v)} /></div>
                      : <p className="text-xs font-medium text-muted-foreground">Mahasiswa {i + 1}</p>}
                    <Button size="sm" variant="ghost" className="h-6 shrink-0 px-2 text-xs"
                            onClick={() => hapus(daftar, i)}>Hapus</Button>
                  </div>
                  {kolom.map(([k, l]) => (
                    <Isian key={k} label={l} nilai={butir[k]}
                           onChange={v => setDalam(daftar, i, k, v)} />
                  ))}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {pesan && <p className="mt-4 text-sm text-amber-500">{pesan}</p>}
    </Panel>
  )
}
