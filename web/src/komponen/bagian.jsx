// Potongan tampilan yang dipakai ulang di beberapa tab.
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export function Kartu({ label, nilai, lebar }) {
  return (
    <div className={`rounded-md border bg-muted/40 px-2.5 py-2 dark:bg-background ${lebar || ""}`}>
      <p className="truncate text-sm font-semibold leading-tight" title={String(nilai)}>{nilai}</p>
      {/* Label sengaja sewarna teks utama, bukan abu-abu: kartu ini dibaca
          sambil menunduk sebentar di atas motor, sering di bawah matahari. */}
      <p className="text-[11px] leading-tight text-foreground">{label}</p>
    </div>
  )
}

export function Baris({ utama, kecil, anak }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b py-2.5 last:border-0">
      <div className="min-w-0">
        <p className="truncate text-sm">{utama}</p>
        <p className="truncate text-xs text-muted-foreground">{kecil}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">{anak}</div>
    </div>
  )
}

// Kartu dengan judul ringkas; `kelas` dipakai untuk menentukan lebar kolomnya
// di dalam grid, sehingga tata letak diatur di tempat pemanggilan.
export function Panel({ judul, kelas, aksi, children }) {
  return (
    <Card className={`gap-0 py-4 ${kelas || ""}`}>
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0 px-4 pb-3">
        <CardTitle className="text-sm">{judul}</CardTitle>
        {aksi}
      </CardHeader>
      <CardContent className="px-4">{children}</CardContent>
    </Card>
  )
}
