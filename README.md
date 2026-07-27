# Willpedia

Website statis Willpedia untuk GitHub Pages. Data produk, rating, ulasan yang
disetujui, dan gambar produk disinkronkan melalui Cloudflare Worker ke Google
Apps Script.

## Deployment website

Gunakan **GitHub Actions** sebagai sumber GitHub Pages. Di repository buka
**Settings → Pages → Build and deployment**, lalu pilih **GitHub Actions**.
Workflow `.github/workflows/deploy-pages.yml` hanya menerbitkan file yang
diperlukan pengunjung.

## Sinkronisasi Google Sheet

Workflow `.github/workflows/sync-sheet-json.yml` berjalan berkala dan dapat
dijalankan manual melalui tab **Actions**.

Repository variables yang dapat digunakan:

- `WILLPEDIA_API_URL` — default `https://api.willpedia.com`
- `WILLPEDIA_API_FALLBACK_URL` — default route `workers.dev`

Jika custom domain terkena respons 403 untuk request otomatis, script mencoba
endpoint fallback. Pesan error sinkronisasi menyertakan host dan status HTTP agar
penyebabnya lebih mudah dilacak.

## Konfigurasi server

Cloudflare Worker membutuhkan:

- `APPS_SCRIPT_URL` — URL deployment Apps Script yang berakhiran `/exec`
- `PROXY_SECRET` — harus sama dengan Script Property `PROXY_SECRET`

Jangan menaruh URL Apps Script atau `PROXY_SECRET` pada JavaScript frontend atau
repository publik. Validasi ulasan, voucher, harga, kuota, rate limit, dan
otorisasi tetap dilakukan di Apps Script.

## Struktur ulasan

Ulasan terikat langsung ke game, bukan ID produk. Header sheet `Komentar`:

`ID_Komentar | Game | Nama | Rating | Komentar | Tanggal | Status`

Lihat `UPDATE-PANDUAN.txt` untuk langkah pemasangan versi terbaru.

## Panduan mengubah kode

Lihat `CODE-GUIDE.md` untuk lokasi file yang perlu diedit, kata kunci fungsi utama,
dan langkah aman setelah mengubah CSS atau data.
