from http.server import BaseHTTPRequestHandler
import json
import re
import urllib.parse

from yt_dlp import YoutubeDL


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


class handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            url = (qs.get("url") or [""])[0].strip()
            if not url or not re.match(r"^https?://", url):
                return self._send(400, {
                    "ok": False,
                    "error": "URL-nya nggak valid. Tempel link video yang lengkap ya.",
                })
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
                return self._send(200, {
                    "ok": False,
                    "error": "Nggak ketemu file videonya di link itu 😅",
                })
            return self._send(200, {
                "ok": True,
                "platform": _platform(url),
                "title": info.get("title") or "Video",
                "thumbnail": info.get("thumbnail") or "",
                "download_url": media_url,
                "ext": info.get("ext") or "mp4",
            })
        except Exception as e:  # noqa: BLE001 - sederhanakan untuk user
            msg = str(e).lower()
            if ("sign in" in msg or "confirm you're not a bot" in msg
                    or "403" in msg or "forbidden" in msg):
                err = ("Platform ini ngeblokir server gratis 😅 "
                       "Coba link TikTok / Instagram / X.")
            elif "unsupported url" in msg:
                err = "Link ini nggak didukung. Coba TikTok / Instagram / X / Facebook."
            elif "private" in msg:
                err = "Videonya private — cuma video publik yang bisa diambil."
            else:
                err = "Gagal ambil video. Coba lagi atau pakai link lain."
            return self._send(200, {"ok": False, "error": err})
