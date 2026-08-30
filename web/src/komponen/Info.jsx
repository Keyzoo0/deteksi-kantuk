import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { aksi, ambil } from "@/lib/api"

// Satu daftar bidang dipakai untuk mode baca maupun mode ubah, supaya
// menambah isian baru cukup satu baris di sini.
const BIDANG = [
  ["judul", "Judul Dokumen", true],
  ["jenis_dokumen", "Jenis Dokumen"],
  ["nomor_dokumen", "Nomor Dokumen"],
  ["nomor_revisi", "Nomor Revisi"],
  ["nama_file", "Nama File"],
  ["tanggal_terbit", "Tanggal Penerbitan"],
  ["unit_penerbit", "Unit Penerbit"],
  ["jumlah_halaman", "Jumlah Halaman"],
  ["universitas", "Universitas / Fakultas", true],
  ["departemen", "Departemen"],
  ["jurusan", "Jurusan"],
  ["alamat", "Alamat", true],
  ["kontak", "Kontak", true],
]

function Bidang({ label, nilai, ubah, onChange, lebar }) {
  return (
    <div className={lebar ? "sm:col-span-2" : undefined}>
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {ubah
        ? <Input className="mt-1" value={nilai || ""} onChange={e => onChange(e.target.value)} />
        : <p className="mt-1 text-sm break-words">
            {nilai || <span className="text-muted-foreground">—</span>}</p>}
    </div>
  )
}

export default function Info({ info, setInfo, setVersiLogo }) {
  const [ubah, setUbah] = useState(false)
  const [draf, setDraf] = useState({})
  const [pesan, setPesan] = useState("")
  const [versiLogo, setVersiLokal] = useState(0)
  const berkas = useRef(null)

  useEffect(() => { setDraf(structuredClone(info || {})) }, [info])
  if (!info) return <p className="text-sm text-muted-foreground">memuat…</p>

  const tampil = ubah ? draf : info
  const set = (kunci, nilai) => setDraf({ ...draf, [kunci]: nilai })
  const setDalam = (daftar, i, kunci, nilai) => {
    const salinan = structuredClone(draf)
    salinan[daftar][i][kunci] = nilai
    setDraf(salinan)
  }
  const tambah = (daftar, isi) =>
    setDraf({ ...draf, [daftar]: [...(draf[daftar] || []), isi] })
  const hapus = (daftar, i) =>
    setDraf({ ...draf, [daftar]: draf[daftar].filter((_, n) => n !== i) })

  async function simpan() {
    const r = await aksi({ perintah: "simpan_info", info: draf })
    setPesan(r.pesan || (r.ok ? "tersimpan" : "gagal menyimpan"))
    if (r.ok) { setUbah(false); ambil("/info").then(setInfo) }
  }

  async function gantiLogo(e) {
    const f = e.target.files?.[0]
    if (!f) return
    if (f.size > 2 * 1024 * 1024) return setPesan("berkas lebih dari 2 MB")
    const pembaca = new FileReader()
    pembaca.onload = async () => {
      const r = await aksi({ perintah: "simpan_logo", data: pembaca.result })
      setPesan(r.pesan || (r.ok ? "logo diganti" : "gagal mengganti logo"))
      if (r.ok) {                          // paksa peramban memuat ulang gambar
        const v = Date.now()
        setVersiLokal(v)
        setVersiLogo?.(v)                  // header ikut menyegarkan logonya
      }
    }
    pembaca.readAsDataURL(f)
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
          <CardTitle className="text-sm">Lembar sampul dokumen</CardTitle>
          <div className="flex shrink-0 gap-2">
            {ubah ? <>
              <Button size="sm" onClick={simpan}>Simpan</Button>
              <Button size="sm" variant="secondary"
                      onClick={() => { setDraf(structuredClone(info)); setUbah(false) }}>Batal</Button>
            </> : <Button size="sm" variant="secondary" onClick={() => setUbah(true)}>Edit</Button>}
          </div>
        </CardHeader>
        <CardContent>
          <div className="mb-6 flex items-center gap-4">
            <img src={`/logo?v=${versiLogo}`} alt="logo universitas"
                 className="size-20 rounded-md border bg-white/5 object-contain p-1" />
            <div>
              <p className="text-sm font-medium">Logo universitas</p>
              <p className="mb-2 text-xs text-muted-foreground">PNG/JPG, maksimal 2 MB.</p>
              <input ref={berkas} type="file" accept="image/*" className="hidden" onChange={gantiLogo} />
              {ubah && <Button size="sm" variant="secondary"
                               onClick={() => berkas.current.click()}>Ganti logo</Button>}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {BIDANG.map(([kunci, label, lebar]) => (
              <Bidang key={kunci} label={label} lebar={lebar} ubah={ubah}
                      nilai={tampil[kunci]} onChange={v => set(kunci, v)} />
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm">Data pengusul</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {(tampil.mahasiswa || []).map((m, i) => (
            <div key={i} className="grid gap-4 rounded-md border p-3 sm:grid-cols-2">
              <div className="flex items-center justify-between sm:col-span-2">
                <p className="text-xs font-medium text-muted-foreground">Mahasiswa {i + 1}</p>
                {ubah && <Button size="sm" variant="ghost"
                                 onClick={() => hapus("mahasiswa", i)}>Hapus</Button>}
              </div>
              <Bidang label="Nama" nilai={m.nama} ubah={ubah}
                      onChange={v => setDalam("mahasiswa", i, "nama", v)} />
              <Bidang label="NIM" nilai={m.nim} ubah={ubah}
                      onChange={v => setDalam("mahasiswa", i, "nim", v)} />
            </div>
          ))}
          {ubah && <Button size="sm" variant="secondary"
                           onClick={() => tambah("mahasiswa", { nama: "", nim: "" })}>
            + Tambah mahasiswa</Button>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm">Pembimbing</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {(tampil.pembimbing || []).map((p, i) => (
            <div key={i} className="grid gap-4 rounded-md border p-3 sm:grid-cols-2">
              <div className="flex items-center justify-between sm:col-span-2">
                <Bidang label="Peran" nilai={p.peran} ubah={ubah}
                        onChange={v => setDalam("pembimbing", i, "peran", v)} />
                {ubah && <Button size="sm" variant="ghost"
                                 onClick={() => hapus("pembimbing", i)}>Hapus</Button>}
              </div>
              <Bidang label="Nama" nilai={p.nama} ubah={ubah}
                      onChange={v => setDalam("pembimbing", i, "nama", v)} />
              <Bidang label="NIP" nilai={p.nip} ubah={ubah}
                      onChange={v => setDalam("pembimbing", i, "nip", v)} />
            </div>
          ))}
          {ubah && <Button size="sm" variant="secondary"
                           onClick={() => tambah("pembimbing", { peran: "", nama: "", nip: "" })}>
            + Tambah pembimbing</Button>}
        </CardContent>
      </Card>

      {pesan && <p className="text-sm text-amber-500">{pesan}</p>}
    </div>
  )
}
