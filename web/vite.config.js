import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// Hasil build ditaruh di web/dist dan disajikan langsung oleh server Python di
// Raspberry Pi, jadi Pi tidak perlu Node sama sekali. base "./" supaya aset
// tetap ketemu dari alamat mana pun.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    // `npm run dev` di laptop tetap bisa memanggil API alat yang sebenarnya.
    proxy: {
      "/data": "http://deteksikantuk.local:8080",
      "/aksi": "http://deteksikantuk.local:8080",
      "/info": "http://deteksikantuk.local:8080",
      "/logo": "http://deteksikantuk.local:8080",
      "/video": "http://deteksikantuk.local:8080",
    },
  },
})
