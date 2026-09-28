/**
 * Audit kontras seluruh teks di halaman web, tema terang maupun gelap.
 *
 * Halaman dibuka sungguhan di Chromium (Puppeteer) lalu tiap teks diukur dari
 * warna hasil render -- termasuk warna yang berasal dari token tema, lapisan
 * semitransparan, dan properti opacity. Ini menangkap hal yang tidak terlihat
 * dari membaca CSS saja, mis. teks berwarna di atas latar bertumpuk.
 *
 * Ambang WCAG: 4,5:1 untuk teks biasa; 3:1 untuk teks besar (>=24px, atau
 * >=18,66px bila tebal).
 *
 * Jalankan (butuh server skenario/alat yang hidup):
 *   cd web && node ../tools/cek_kontras_web.mjs http://127.0.0.1:8101 ...
 */
import { createRequire } from "node:module"

// puppeteer-core hidup di web/node_modules (satu-satunya folder npm di repo
// ini), sedangkan skrip ada di tools/ -- jadi modulnya dicari dari sana.
const butuh = createRequire(new URL("../web/package.json", import.meta.url))
const puppeteer = butuh("puppeteer-core")

const alamat = process.argv.slice(2)
if (!alamat.length) {
  console.error("pakai: node tools/cek_kontras_web.mjs <url> [url ...]")
  process.exit(2)
}

const audit = () => {
  // Chromium mengembalikan warna apa adanya (mis. "oklch(0.145 0 0)"), jadi
  // konversinya diserahkan ke canvas: apa pun format CSS-nya, yang terbaca
  // adalah piksel yang benar-benar digambar.
  const kanvas = document.createElement("canvas")
  kanvas.width = kanvas.height = 1
  const kuas = kanvas.getContext("2d", { willReadFrequently: true })
  kuas.globalCompositeOperation = "copy"
  const urai = (c) => {
    if (!c || c === "transparent" || c === "none") return { r: 0, g: 0, b: 0, a: 0 }
    kuas.fillStyle = "#123456"                 // penanda: kalau nilai tak sah, tetap ini
    kuas.fillStyle = c
    if (kuas.fillStyle === "#123456" && c.replace(/\s/g, "") !== "#123456") return null
    kuas.fillRect(0, 0, 1, 1)
    const d = kuas.getImageData(0, 0, 1, 1).data
    // getImageData memberi nilai TANPA premultiplikasi alfa, jadi komponen
    // warnanya dipakai apa adanya.
    return { r: d[0], g: d[1], b: d[2], a: d[3] / 255 }
  }
  // Alfa hasil ikut dihitung: latar bertumpuk seperti bg-emerald-500/10 di
  // atas kartu tetap tembus pandang, jadi pemanjatan ke induk harus lanjut.
  const timpa = (atas, bawah) => {
    const a = atas.a + bawah.a * (1 - atas.a)
    if (!a) return { r: 0, g: 0, b: 0, a: 0 }
    const c = (x, y) => (x * atas.a + y * bawah.a * (1 - atas.a)) / a
    return { r: c(atas.r, bawah.r), g: c(atas.g, bawah.g), b: c(atas.b, bawah.b), a }
  }
  const lum = ({ r, g, b }) => {
    const k = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }
    return 0.2126 * k(r) + 0.7152 * k(g) + 0.0722 * k(b)
  }
  // Latar efektif: naik ke induk sampai ketemu warna tak tembus pandang.
  const latar = (el) => {
    let hasil = null
    for (let n = el; n; n = n.parentElement) {
      const c = urai(getComputedStyle(n).backgroundColor)
      if (!c || !c.a) continue
      hasil = hasil ? timpa(hasil, c) : c
      if (hasil.a >= 1) return hasil
    }
    return hasil || { r: 255, g: 255, b: 255, a: 1 }
  }
  const opasitas = (el) => {
    let o = 1
    for (let n = el; n; n = n.parentElement) o *= +getComputedStyle(n).opacity
    return o
  }

  const temuan = []
  for (const el of document.querySelectorAll("body *")) {
    const teks = [...el.childNodes]
      .filter((n) => n.nodeType === 3 && n.textContent.trim())
      .map((n) => n.textContent.trim()).join(" ")
    if (!teks) continue
    const g = getComputedStyle(el)
    const kotak = el.getBoundingClientRect()
    if (!kotak.width || !kotak.height || g.visibility === "hidden") continue
    const o = opasitas(el)
    if (o < 0.05) continue
    const depan = urai(g.color)
    if (!depan) continue
    const bg = latar(el)
    const efektif = timpa({ ...depan, a: depan.a * o }, bg)
    const [a, b] = [lum(efektif), lum(bg)].sort((x, y) => y - x)
    const rasio = (a + 0.05) / (b + 0.05)
    const px = parseFloat(g.fontSize)
    const tebal = +g.fontWeight >= 700
    const ambang = px >= 24 || (tebal && px >= 18.66) ? 3 : 4.5
    temuan.push({
      teks: teks.slice(0, 42), rasio: +rasio.toFixed(2), ambang, px: +px.toFixed(1),
      warna: g.color, lulus: rasio >= ambang,
      kelas: (el.className || "").toString().slice(0, 60),
      induk: (el.parentElement?.className || "").toString().slice(0, 60),
    })
  }
  return temuan
}

const jalankan = async () => {
  const browser = await puppeteer.launch({
    executablePath: "/usr/bin/chromium",
    headless: "new",
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
  })
  let gagal = 0
  for (const url of alamat) {
    for (const tema of ["terang", "gelap"]) {
      const page = await browser.newPage()
      await page.setViewport({ width: 1440, height: 1200 })
      await page.evaluateOnNewDocument((t) => { try { localStorage.setItem("tema", t) } catch {} }, tema)
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 })
      await page.waitForSelector("header", { timeout: 20000 })
      await new Promise((r) => setTimeout(r, 2500))          // tunggu /data masuk
      // Tiap tab diperiksa: teks di tab yang tidak aktif tidak dirender sama
      // sekali, jadi audit satu layar saja melewatkan sebagian besar halaman.
      const temuan = []
      for (const tab of ["Dashboard", "Settings", "Info"]) {
        const ketemu = await page.evaluate((nama) => {
          const t = [...document.querySelectorAll("button, [role=tab]")]
            .find((e) => e.textContent.trim() === nama)
          if (t) t.click()
          return !!t
        }, tab)
        if (!ketemu) continue
        await new Promise((r) => setTimeout(r, 900))
        temuan.push(...(await page.evaluate(audit)).map((t) => ({ ...t, tab })))
      }
      const buruk = temuan.filter((t) => !t.lulus)
      gagal += buruk.length
      const min = temuan.reduce((a, t) => (t.rasio < a.rasio ? t : a), temuan[0])
      console.log(`\n${url}  tema ${tema}  -- ${temuan.length} teks diperiksa, ` +
                  `${buruk.length} di bawah ambang`)
      console.log(`  paling tipis: ${min.rasio}:1 (min ${min.ambang}) "${min.teks}" [${min.tab}]`)
      for (const t of buruk.slice(0, 12)) {
        console.log(`  [GAGAL] ${String(t.rasio).padStart(5)}:1 (min ${t.ambang}) ` +
                    `${t.px}px  [${t.tab}] "${t.teks}"\n          warna ${t.warna}\n` +
                    `          kelas ${t.kelas}\n          induk ${t.induk}`)
      }
      await page.close()
    }
  }
  await browser.close()
  console.log(`\n${"=".repeat(58)}`)
  console.log(gagal ? `${gagal} teks di bawah ambang kontras.` : "Semua teks memenuhi ambang kontras.")
  process.exit(gagal ? 1 : 0)
}
jalankan()
