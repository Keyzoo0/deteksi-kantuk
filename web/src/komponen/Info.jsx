import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Panel } from "@/komponen/bagian"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { aksi, ambil } from "@/lib/api"

// Satu daftar bidang dipakai untuk mode baca maupun mode ubah, supaya
// menambah isian baru cukup satu baris di sini.
// Dipisah dua kelompok supaya kolom kiri (identitas lembaga, jarang berubah)
// tidak berebut ruang dengan lembar sampul yang isinya lebih banyak.
const IDENTITAS = [
  ["universitas", "Universitas / Fakultas"],
  ["departemen", "Departemen"],
  ["jurusan", "Jurusan"],
  ["alamat", "Alamat"],
  ["kontak", "Kontak"],
]
const DOKUMEN = [
  ["judul", "Judul Dokumen", 4],
  ["jenis_dokumen", "Jenis Dokumen"],
  ["nomor_revisi", "Nomor Revisi"],
  ["jumlah_halaman", "Jumlah Halaman"],
  ["tanggal_terbit", "Tanggal Penerbitan"],
  ["nomor_dokumen", "Nomor Dokumen", 2],
  ["nama_file", "Nama File", 2],
  ["unit_penerbit", "Unit Penerbit", 2],
]

const RENTANG = { 2: "sm:col-span-2", 3: "sm:col-span-3", 4: "sm:col-span-4" }

function Bidang({ label, nilai, ubah, onChange, lebar }) {
  return (
    <div className={RENTANG[lebar]}>
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
    <div className="grid gap-4 xl:grid-cols-12">
      <Panel judul="Identitas" kelas="xl:col-span-4">
        <div className="mb-4 flex items-center gap-4">
          <img src={`/logo?v=${versiLogo}`} alt="logo universitas"
               className="size-20 shrink-0 rounded-md border bg-background object-contain p-1.5" />
          <div>
            <p className="text-sm font-medium">Logo universitas</p>
            <p className="mb-2 text-xs text-muted-foreground">PNG/JPG, maksimal 2 MB.</p>
            <input ref={berkas} type="file" accept="image/*" className="hidden" onChange={gantiLogo} />
            {ubah
              ? <Button size="sm" variant="secondary" onClick={() => berkas.current.click()}>
                  Ganti logo</Button>
              : <p className="text-xs text-muted-foreground">Tekan Edit untuk menggantinya.</p>}
          </div>
        </div>
        <div className="grid gap-3">
          {IDENTITAS.map(([kunci, label]) => (
            <Bidang key={kunci} label={label} ubah={ubah}
                    nilai={tampil[kunci]} onChange={v => set(kunci, v)} />
          ))}
        </div>
      </Panel>

      <Panel judul="Lembar sampul dokumen" kelas="xl:col-span-8"
        aksi={ubah
          ? <div className="flex gap-2">
              <Button size="sm" onClick={simpan}>Simpan</Button>
              <Button size="sm" variant="secondary"
                      onClick={() => { setDraf(structuredClone(info)); setUbah(false) }}>Batal</Button>
            </div>
          : <Button size="sm" variant="secondary" onClick={() => setUbah(true)}>Edit</Button>}>
        <div className="grid gap-3 sm:grid-cols-4">
          {DOKUMEN.map(([kunci, label, lebar]) => (
            <Bidang key={kunci} label={label} lebar={lebar} ubah={ubah}
                    nilai={tampil[kunci]} onChange={v => set(kunci, v)} />
          ))}
        </div>
      </Panel>

      <Panel judul="Data pengusul" kelas="xl:col-span-6"
        aksi={ubah && <Button size="sm" variant="secondary"
          onClick={() => tambah("mahasiswa", { nama: "", nim: "" })}>+ Tambah</Button>}>
        <div className="grid gap-3 sm:grid-cols-2">
          {(tampil.mahasiswa || []).map((m, i) => (
            <div key={i} className="grid gap-3 rounded-md border p-3">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-muted-foreground">Mahasiswa {i + 1}</p>
                {ubah && <Button size="sm" variant="ghost" className="h-6 px-2 text-xs"
                                 onClick={() => hapus("mahasiswa", i)}>Hapus</Button>}
              </div>
              <Bidang label="Nama" nilai={m.nama} ubah={ubah}
                      onChange={v => setDalam("mahasiswa", i, "nama", v)} />
              <Bidang label="NIM" nilai={m.nim} ubah={ubah}
                      onChange={v => setDalam("mahasiswa", i, "nim", v)} />
            </div>
          ))}
        </div>
      </Panel>

      <Panel judul="Pembimbing" kelas="xl:col-span-6"
        aksi={ubah && <Button size="sm" variant="secondary"
          onClick={() => tambah("pembimbing", { peran: "", nama: "", nip: "" })}>+ Tambah</Button>}>
        <div className="grid gap-3 sm:grid-cols-2">
          {(tampil.pembimbing || []).map((p, i) => (
            <div key={i} className="grid gap-3 rounded-md border p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <Bidang label="Peran" nilai={p.peran} ubah={ubah}
                          onChange={v => setDalam("pembimbing", i, "peran", v)} />
                </div>
                {ubah && <Button size="sm" variant="ghost" className="mt-4 h-6 px-2 text-xs"
                                 onClick={() => hapus("pembimbing", i)}>Hapus</Button>}
              </div>
              <Bidang label="Nama" nilai={p.nama} ubah={ubah}
                      onChange={v => setDalam("pembimbing", i, "nama", v)} />
              <Bidang label="NIP" nilai={p.nip} ubah={ubah}
                      onChange={v => setDalam("pembimbing", i, "nip", v)} />
            </div>
          ))}
        </div>
      </Panel>

      {pesan && <p className="text-sm text-amber-500 xl:col-span-12">{pesan}</p>}
    </div>
  )
}
