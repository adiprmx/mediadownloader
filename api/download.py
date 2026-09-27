from http.server import BaseHTTPRequestHandler
import http.client
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request

from yt_dlp import YoutubeDL

# Header ala browser — dibutuhkan API tikwm agar tidak ditolak.
TIKWM_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) "
                   "Gecko/20100101 Firefox/141.0"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Origin": "https://tikwm.com",
    "Referer": "https://tikwm.com/",
    "x-requested-with": "XMLHttpRequest",
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _platform(url: str) -> str:
    u = url.lower()
    if "tiktok.com" in u:
        return "TikTok"
    if "instagram.com" in u:
        return "Instagram"
    if "twitter.com" in u or "x.com" in u:
        return "X (Twitter)"
    if "youtube.com" in u or "youtu.be" in u:
        return "YouTube"
    if "facebook.com" in u or "fb.watch" in u:
        return "Facebook"
    return "Video"


def _pick_url(info: dict) -> str | None:
    """Pilih direct URL video terbaik; utamakan yang tanpa watermark."""
    fmts = info.get("formats") or []
    vids = [f for f in fmts if f.get("url") and f.get("vcodec") != "none"]

    def no_wm(f: dict) -> bool:
        blob = f"{f.get('format_id', '')} {f.get('format_note', '')}".lower()
        return "watermark" not in blob

    pool = [f for f in vids if no_wm(f)] or vids
    pool.sort(
        key=lambda f: (
            f.get("height") or 0,
            f.get("filesize") or f.get("filesize_approx") or 0,
        ),
        reverse=True,
    )
    if pool:
        return pool[0].get("url")
    return info.get("url")


def _extract_tikwm(url: str) -> dict | None:
    """Fallback TikTok via API gratis tikwm. Bisa video maupun foto (slideshow)."""
    for _ in range(3):  # API gratis kadang flaky → coba 3x
        res = _tikwm_once(url)
        if res:
            return res
    return None


def _tikwm_fetch(url: str) -> dict | None:
    """Ambil JSON dari tikwm via curl (transport paling bisa diandelin di sini)."""
    q = urllib.parse.urlencode({"url": url, "hd": 1})
    api = f"https://www.tikwm.com/api/?{q}"
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "25",
             "-A", TIKWM_HEADERS["User-Agent"],
             "-H", f"Accept: {TIKWM_HEADERS['Accept']}",
             "-H", f"Origin: {TIKWM_HEADERS['Origin']}",
             "-H", f"Referer: {TIKWM_HEADERS['Referer']}",
             "-H", f"x-requested-with: {TIKWM_HEADERS['x-requested-with']}",
             api],
            capture_output=True, text=True, timeout=30)
        if r.returncode != 0 or not r.stdout.strip():
            return None
        return json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        return None


def _tikwm_once(url: str) -> dict | None:
    data = _tikwm_fetch(url)
    if not data:
        return None
    try:
        if data.get("code") != 0:
            return None
        d = data.get("data") or {}
        play = d.get("hdplay") or d.get("play") or d.get("wmplay")
        images = d.get("images") or []
        if not play and not images:
            return None
        author = d.get("author") or {}
        uname = author.get("unique_id") or "tiktok"
        # Post foto (/photo/) → tampilkan galeri foto, bukan video slideshow
        is_photos = "/photo/" in url.lower() or (bool(images) and not play)
        if is_photos and not images and play:
            # fallback: foto tak ada tapi ada video → tampilkan sebagai video
            is_photos = False
        return {
            "ok": True,
            "platform": "TikTok",
            "title": d.get("title") or f"{'Foto' if is_photos else 'Video'} TikTok @{uname}",
            "thumbnail": (images[0] if is_photos and images else None) or d.get("cover") or "",
            "download_url": "" if is_photos else (play or ""),
            "images": images if is_photos else [],
            "media_type": "photos" if is_photos else "video",
            "ext": "mp4",
        }
    except Exception:  # noqa: BLE001 - fallback memang boleh gagal diam-diam
        return None


def _extract(url: str) -> dict:
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 12,
            "format": "best",
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        # yt-dlp gagal (sering karena IP server diblokir) → coba fallback TikTok
        if "tiktok.com" in url.lower():
            fb = _extract_tikwm(url)
            if fb:
                return fb
        raise
    media_url = _pick_url(info)
    if not media_url:
        return {"ok": False, "error": "Nggak ketemu file videonya di link itu 😅"}
    return {
        "ok": True,
        "platform": _platform(url),
        "title": info.get("title") or "Video",
        "thumbnail": info.get("thumbnail") or "",
        "download_url": media_url,
        "images": [],
        "media_type": "video",
        "ext": info.get("ext") or "mp4",
    }


def _friendly_error(e: Exception, url: str = "") -> str:
    msg = (str(e) + " " + url).lower()
    if ("sign in" in msg or "confirm you're not a bot" in msg
            or "403" in msg or "forbidden" in msg):
        return ("Server gratis diblokir platform ini 😅 "
                "TikTok biasanya bisa — coba lagi. "
                "Instagram / X / YouTube sering gagal dari server gratis.")
    if "unsupported url" in msg:
        return "Link ini nggak didukung. Coba TikTok / Instagram / X / Facebook."
    if "private" in msg:
        return "Videonya private — cuma video publik yang bisa diambil."
    if "cannot parse data" in msg and "facebook" in msg:
        return ("Facebook nolak akses server 😅 "
                "Video Facebook publik kadang bisa — coba link lain, "
                "atau pakai TikTok yang paling lancar.")
    return "Gagal ambil video. Coba lagi atau pakai link lain."


class handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, filename: str, ctype: str) -> None:
        path = os.path.join(ROOT, filename)
        if not os.path.isfile(path):
            self.send_response(404)
            self.end_headers()
            return
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            return self._serve_file("index.html", "text/html; charset=utf-8")
        if parsed.path == "/api/download":
            try:
                qs = urllib.parse.parse_qs(parsed.query)
                url = (qs.get("url") or [""])[0].strip()
                if not url or not re.match(r"^https?://", url):
                    return self._send(400, {
                        "ok": False,
                        "error": "URL-nya nggak valid. Tempel link video yang lengkap ya.",
                    })
                final = url
                if "facebook.com/groups/" in final.lower():
                    return self._send(200, {"ok": False, "error": (
                        "Itu postingan grup Facebook — butuh login buat dibuka, "
                        "jadi server nggak bisa ambil 😅 Coba video Facebook "
                        "yang publik (dari halaman/reels publik).")})
                return self._send(200, _extract(url))
            except Exception as e:  # noqa: BLE001 - sederhanakan untuk user
                return self._send(200, {"ok": False, "error": _friendly_error(e, url)})
        self.send_response(404)
        self.end_headers()
