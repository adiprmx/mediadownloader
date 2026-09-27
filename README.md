# ADIP Downloader

Website downloader video — tempel link, download langsung. Gratis, jalan di Vercel free tier.

**Support:** TikTok, Instagram, X/Twitter, Facebook (video publik).
**Nggak support:** YouTube (diblokir dari IP server gratis), video private.

## Cara deploy (gratis)

1. Import repo ini di [vercel.com](https://vercel.com) → Add New → Project
2. Deploy. Selesai.

## Cara kerja

- `index.html` — tampilan (mobile-first)
- `api/download.py` — serverless function, pakai `yt-dlp` buat ekstrak direct URL video, lalu user download langsung dari CDN (server nggak ikut download → ringan)
