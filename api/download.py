from http.server import BaseHTTPRequestHandler
import json
import os
import re
import urllib.parse

from yt_dlp import YoutubeDL

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


def _extract(url: str) -> dict:
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
    media_url = _pick_url(info)
    if not media_url:
        return {"ok": False, "error": "Nggak ketemu file videonya di link itu 😅"}
    return {
        "ok": True,
        "platform": _platform(url),
        "title": info.get("title") or "Video",
        "thumbnail": info.get("thumbnail") or "",
        "download_url": media_url,
        "ext": info.get("ext") or "mp4",
    }


def _friendly_error(e: Exception) -> str:
    msg = str(e).lower()
    if ("sign in" in msg or "confirm you're not a bot" in msg
            or "403" in msg or "forbidden" in msg):
        return ("Platform ini ngeblokir server gratis 😅 "
                "Coba link TikTok / Instagram / X.")
    if "unsupported url" in msg:
        return "Link ini nggak didukung. Coba TikTok / Instagram / X / Facebook."
    if "private" in msg:
        return "Videonya private — cuma video publik yang bisa diambil."
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
                return self._send(200, _extract(url))
            except Exception as e:  # noqa: BLE001 - sederhanakan untuk user
                return self._send(200, {"ok": False, "error": _friendly_error(e)})
        self.send_response(404)
        self.end_headers()
