// Pembungkus tipis panggilan ke alat. Semua rute disajikan server Python di
// Raspberry Pi (src/web.py); saat `npm run dev`, Vite mem-proxy-kannya ke alat.

export async function ambil(rute) {
  const r = await fetch(rute)
  if (!r.ok) throw new Error(rute + " gagal")
  return r.json()
}

export async function aksi(badan) {
  const r = await fetch("/aksi", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(badan),
  })
  return r.json()
}
