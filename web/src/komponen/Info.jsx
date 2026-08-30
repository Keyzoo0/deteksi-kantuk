import { Panel } from "@/komponen/bagian"

// Tab Info hanya MENAMPILKAN lembar sampul dokumen. Pengubahannya ada di tab
// Settings supaya halaman yang dilihat sehari-hari bersih dari tombol dan
// kotak isian.
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

function Nilai({ label, nilai, lebar }) {
  return (
    <div className={RENTANG[lebar]}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm break-words">
        {nilai || <span className="text-muted-foreground">—</span>}</p>
    </div>
  )
}

export default function Info({ info, versiLogo }) {
  if (!info) return <p className="text-sm text-muted-foreground">memuat…</p>

  return (
    <div className="grid gap-4 xl:grid-cols-12">
      <Panel judul="Identitas" kelas="xl:col-span-4">
        <div className="mb-4 flex items-center gap-4">
          <img src={`/logo?v=${versiLogo}`} alt="logo universitas"
               className="size-20 shrink-0 rounded-md border bg-background object-contain p-1.5" />
          <div className="min-w-0">
            <p className="text-sm font-medium break-words">{info.universitas}</p>
            <p className="text-xs text-muted-foreground break-words">{info.departemen}</p>
          </div>
        </div>
        <div className="grid gap-3">
          {IDENTITAS.map(([kunci, label]) => (
            <Nilai key={kunci} label={label} nilai={info[kunci]} />
          ))}
        </div>
      </Panel>

      <Panel judul="Lembar sampul dokumen" kelas="xl:col-span-8">
        <div className="grid gap-3 sm:grid-cols-4">
          {DOKUMEN.map(([kunci, label, lebar]) => (
            <Nilai key={kunci} label={label} lebar={lebar} nilai={info[kunci]} />
          ))}
        </div>
      </Panel>

      <Panel judul="Data pengusul" kelas="xl:col-span-6">
        <div className="grid gap-3 sm:grid-cols-2">
          {(info.mahasiswa || []).map((m, i) => (
            <div key={i} className="grid gap-3 rounded-md border p-3">
              <p className="text-xs font-medium text-muted-foreground">Mahasiswa {i + 1}</p>
              <Nilai label="Nama" nilai={m.nama} />
              <Nilai label="NIM" nilai={m.nim} />
            </div>
          ))}
        </div>
      </Panel>

      <Panel judul="Pembimbing" kelas="xl:col-span-6">
        <div className="grid gap-3 sm:grid-cols-2">
          {(info.pembimbing || []).map((p, i) => (
            <div key={i} className="grid gap-3 rounded-md border p-3">
              <p className="text-xs font-medium text-muted-foreground">{p.peran || `Pembimbing ${i + 1}`}</p>
              <Nilai label="Nama" nilai={p.nama} />
              <Nilai label="NIP" nilai={p.nip} />
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}
