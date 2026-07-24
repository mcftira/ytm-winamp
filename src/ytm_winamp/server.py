"""Localhost bridge: serves YouTube audio to Winamp as a plain MP3 HTTP stream.

Winamp 5.x cannot fetch YouTube's googlevideo URLs directly (the CDN rejects
its HTTP client), so this server does the fetch with yt-dlp and transcodes to
MP3 with ffmpeg on the fly. Stream URLs are resolved lazily per request, which
also sidesteps googlevideo URL expiry.
"""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

DEFAULT_PORT = 8797
_STREAM_RE = re.compile(r"^/stream/([A-Za-z0-9_-]{6,20})(?:\.mp3)?$")

log = logging.getLogger("ytm-winamp")


class BridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "ytm-winamp/0.1"

    def log_message(self, fmt, *args):  # route access logs through logging
        log.info("%s - %s", self.address_string(), fmt % args)

    def _text(self, code: int, body: str) -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/ping":
            self._text(200, "ok")
            return
        match = _STREAM_RE.match(path)
        if not match:
            self._text(404, "not found")
            return
        self._stream(match.group(1))

    def _stream(self, video_id: str) -> None:
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        log.info("streaming %s to %s", video_id, self.client_address)
        # yt-dlp owns the network side (it handles googlevideo's quirks);
        # ffmpeg only sees a seek-free pipe, so prefer streamable webm audio.
        ytdlp = subprocess.Popen(
            ["yt-dlp", "-f", "bestaudio[ext=webm]/bestaudio", "--no-playlist",
             "--no-warnings", "-o", "-", watch_url],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        ffmpeg = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-vn", "-f", "mp3", "-b:a", "192k", "pipe:1"],
            stdin=ytdlp.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        assert ytdlp.stdout is not None
        ytdlp.stdout.close()  # ffmpeg now owns the read end
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            assert ffmpeg.stdout is not None
            shutil.copyfileobj(ffmpeg.stdout, self.wfile, 64 * 1024)
        except OSError:
            # broken pipe / reset / abort: Winamp disconnects and reconnects
            # while buffering, which is normal for streaming clients
            log.info("client disconnected during %s", video_id)
        finally:
            ffmpeg.kill()
            ytdlp.kill()


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    # http.server enables SO_REUSEADDR by default, which on Windows lets a
    # second instance silently bind the same port and steal connections.
    # Refuse to double-bind instead: only one bridge may ever serve a port.
    allow_reuse_address = False


def run(port: int = DEFAULT_PORT) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    for tool in ("yt-dlp", "ffmpeg"):
        if not shutil.which(tool):
            raise SystemExit(f"error: {tool!r} not found on PATH")
    server = BridgeServer(("127.0.0.1", port), BridgeHandler)
    log.info("ytm-winamp bridge listening on http://127.0.0.1:%d", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="ytm-winamp streaming bridge")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    run(parser.parse_args().port)


if __name__ == "__main__":
    main()
