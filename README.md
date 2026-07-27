# Willpedia

Website statis Willpedia untuk GitHub Pages dengan data produk yang
disinkronkan dari Google Apps Script.

## Deployment yang disarankan

Gunakan **GitHub Actions** sebagai sumber GitHub Pages. Workflow
`.github/workflows/deploy-pages.yml` hanya menerbitkan file yang diperlukan
pengunjung. Folder `scripts/`, workflow, cache Python, dan
`data/product-images.json` tetap berada di repository untuk proses
sinkronisasi, tetapi tidak ikut tersedia di website.

Di repository GitHub buka **Settings → Pages → Build and deployment**, lalu
pilih **GitHub Actions** pada bagian Source.

Website dan workflow sinkronisasi memakai Cloudflare Worker sebagai gerbang API.
URL Google Apps Script dan `PROXY_SECRET` tidak boleh ditaruh di repository.
Validasi ulasan, voucher, harga, kuota, rate limit, dan otorisasi tetap wajib
dilakukan di Apps Script.
