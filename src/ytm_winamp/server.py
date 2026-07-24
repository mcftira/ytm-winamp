"""Localhost bridge: serves YouTube audio to Winamp as MP3 over HTTP.

Winamp 5.x cannot fetch YouTube's googlevideo URLs directly (the CDN rejects
its HTTP client), so this server fetches audio with yt-dlp, transcodes it to
MP3 with ffmpeg, and caches tracks on disk. Upcoming tracks are prefetched in
the background, so switching songs in Winamp starts from the cache instantly
instead of waiting for a cold resolve on every track change.

Track titles are injected into the stream as ICY (SHOUTcast-style) metadata
when the player asks for it, so Winamp shows "Artist - Title" instead of the
bare video id once a stream connects.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_PORT = 8797
_STREAM_RE = re.compile(r"^/stream/([A-Za-z0-9_-]{6,20})(?:\.mp3)?$")

CACHE_DIR = Path(tempfile.gettempdir()) / "ytm-winamp-cache"
MAX_CACHE_FILES = 32
PREFETCH_AHEAD = 12      # how many queued tracks to download ahead
START_TIMEOUT = 30       # seconds to wait for a download's first bytes
STALL_TIMEOUT = 45       # seconds without file growth before giving up
FAIL_RETRY_AFTER = 120   # seconds before retrying a failed track
ICY_METAINT = 8192       # bytes of MP3 between ICY metadata blocks

log = logging.getLogger("ytm-winamp")


def icy_block(title: str | None) -> bytes:
    """One ICY metadata block; empty blocks are a single zero byte."""
    if not title:
        return b"\x00"
    meta = f"StreamTitle='{title}';".encode("utf-8", errors="replace")
    pad = 16 - (len(meta) % 16)
    meta += b"\x00" * pad
    return bytes([len(meta) // 16]) + meta


class TrackCache:
    """Downloads tracks to disk in the background; serves files as they grow.

    A track is "ready" when its ``<vid>.mp3`` is fully written and marked with
    an empty ``<vid>.done`` file. The marker avoids renaming files that
    readers may still have open (which Windows forbids).
    """

    def __init__(self, directory: Path = CACHE_DIR, start_worker: bool = True):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._downloading: set[str] = set()
        self._failed: dict[str, float] = {}
        self._queue: list[str] = []
        self._titles: dict[str, str] = {}
        self._wake = threading.Event()
        if start_worker:
            # two workers so one very long download (a mix, a compilation)
            # cannot starve the track the user is actually switching to
            for _ in range(2):
                threading.Thread(target=self._work, daemon=True).start()

    def mp3_path(self, vid: str) -> Path:
        return self.dir / f"{vid}.mp3"

    def done_path(self, vid: str) -> Path:
        return self.dir / f"{vid}.done"

    def is_ready(self, vid: str) -> bool:
        return self.done_path(vid).exists()

    def recently_failed(self, vid: str) -> bool:
        with self._lock:
            ts = self._failed.get(vid, 0.0)
        return time.time() - ts < FAIL_RETRY_AFTER

    def in_progress(self, vid: str) -> bool:
        with self._lock:
            return vid in self._downloading or vid in self._queue

    def set_titles(self, titles: dict[str, str]) -> None:
        with self._lock:
            self._titles.update(titles)

    def title_for(self, vid: str) -> str:
        with self._lock:
            return self._titles.get(vid, vid)

    def prefetch(self, vids: list[str]) -> None:
        """Queue tracks for background download, most important first."""
        with self._lock:
            for vid in vids:  # explicit request clears the retry window
                self._failed.pop(vid, None)
            self._queue = [v for v in vids if not self.is_ready(v)][:PREFETCH_AHEAD]
        self._wake.set()

    def ensure(self, vid: str) -> None:
        """Make sure a track is being downloaded, jumping the queue."""
        if self.is_ready(vid):
            return
        with self._lock:
            self._failed.pop(vid, None)
            if vid in self._queue:
                self._queue.remove(vid)
            self._queue.insert(0, vid)
        self._wake.set()

    def _work(self) -> None:
        while True:
            self._wake.wait()
            self._wake.clear()
            while True:
                with self._lock:
                    if not self._queue:
                        break
                    vid = self._queue.pop(0)
                    if self.is_ready(vid) or vid in self._downloading:
                        continue
                    self._downloading.add(vid)
                try:
                    self._download(vid)
                except Exception:
                    log.exception("unexpected error downloading %s", vid)
                    with self._lock:
                        self._failed[vid] = time.time()
                finally:
                    with self._lock:
                        self._downloading.discard(vid)

    def _download(self, vid: str) -> None:
        for attempt in (1, 2):  # yt-dlp fails transiently; one retry helps
            if self._download_once(vid):
                return
            if attempt == 1:
                time.sleep(3)
        with self._lock:
            self._failed[vid] = time.time()

    def _download_once(self, vid: str) -> bool:
        mp3 = self.mp3_path(vid)
        done = self.done_path(vid)
        for p in (mp3, done):
            p.unlink(missing_ok=True)
        log.info("downloading %s", vid)
        # ffmpeg writes the MP3 straight to disk; webm preferred because a
        # seek-free pipe cannot hold formats with a trailing index (m4a).
        ytdlp = subprocess.Popen(
            ["yt-dlp", "-f", "bestaudio[ext=webm]/bestaudio", "--no-playlist",
             "--no-warnings", "-o", "-", f"https://www.youtube.com/watch?v={vid}"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        ffmpeg = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-i", "pipe:0", "-vn", "-f", "mp3", "-b:a", "192k", str(mp3)],
            stdin=ytdlp.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        assert ytdlp.stdout is not None
        ytdlp.stdout.close()  # ffmpeg owns the read end
        ff_rc = ffmpeg.wait()
        yt_rc = ytdlp.wait()
        if ff_rc == 0 and yt_rc == 0 and mp3.exists() and mp3.stat().st_size > 0:
            done.touch()
            log.info("cached %s (%d bytes)", vid, mp3.stat().st_size)
            self._evict()
            return True
        mp3.unlink(missing_ok=True)
        log.warning("download failed for %s (yt-dlp rc=%s ffmpeg rc=%s)",
                    vid, yt_rc, ff_rc)
        return False

    def _evict(self) -> None:
        ready = [(f.stat().st_mtime, f) for f in self.dir.glob("*.mp3")
                 if self.done_path(f.stem).exists()]
        if len(ready) <= MAX_CACHE_FILES:
            return
        ready.sort()
        for _, f in ready[: len(ready) - MAX_CACHE_FILES]:
            self.done_path(f.stem).unlink(missing_ok=True)
            f.unlink(missing_ok=True)
            log.info("evicted %s", f.stem)


class BridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "ytm-winamp/0.4"

    def log_message(self, fmt, *args):  # route access logs through logging
        log.info("%s - %s", self.address_string(), fmt % args)

    @property
    def cache(self) -> TrackCache:
        return self.server.cache  # type: ignore[attr-defined]

    def _text(self, code: int, body: str) -> None:
        data = body.encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            pass  # client probing or already gone

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

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/prefetch":
            self._text(404, "not found")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"[]")
            if isinstance(data, list):  # legacy: bare list of video ids
                vids, titles = data, {}
            else:
                vids = data["vids"]
                titles = data.get("titles") or {}
            if not isinstance(vids, list):
                raise ValueError
        except (ValueError, AttributeError, TypeError):
            self._text(400, "expected a JSON list of video ids or "
                            '{"vids": [...], "titles": {...}}')
            return
        self.cache.set_titles({str(k): str(v) for k, v in titles.items()})
        self.cache.prefetch([str(v) for v in vids])
        self._text(202, "queued")

    def _wants_icy(self) -> bool:
        return self.headers.get("Icy-MetaData") in ("1", "yes")

    def _stream(self, vid: str) -> None:
        cache = self.cache
        if cache.recently_failed(vid) and not cache.in_progress(vid):
            self._text(502, "track unavailable")
            return
        # ensure() clears any stale failure mark and jumps the download
        # queue, so a Winamp retry always gets a fresh chance
        cache.ensure(vid)
        mp3 = cache.mp3_path(vid)
        deadline = time.time() + START_TIMEOUT
        while not (mp3.exists() and mp3.stat().st_size > 0):
            # only fail the request once nothing is trying anymore;
            # while a (re)download runs, keep waiting for first bytes
            if cache.recently_failed(vid) and not cache.in_progress(vid):
                self._text(502, "track unavailable")
                return
            if time.time() > deadline:
                self._text(504, "timed out starting track")
                return
            time.sleep(0.25)
        title = cache.title_for(vid).replace("'", " ")
        icy = self._wants_icy()
        log.info("streaming %s (%s) to %s%s", vid, title, self.client_address,
                 " [icy]" if icy else "")
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Cache-Control", "no-store")
        if icy:
            self.send_header("icy-metaint", str(ICY_METAINT))
            self.send_header("icy-br", "192")
            self.send_header("icy-name", title)
            # no Content-Length: interleaved metadata blocks shift the total
        elif cache.is_ready(vid):  # complete file: Winamp gets a real length
            self.send_header("Content-Length", str(mp3.stat().st_size))
        self.end_headers()
        try:
            self._pump(vid, mp3, icy, title)
        except OSError:
            # broken pipe / reset / abort: Winamp disconnects and reconnects
            # while buffering, which is normal for streaming clients
            log.info("client disconnected during %s", vid)

    def _pump(self, vid: str, mp3: Path, icy: bool, title: str) -> None:
        with open(mp3, "rb") as f:
            last_growth = time.time()
            since_meta = 0
            sent_title = False
            while True:
                want = (ICY_METAINT - since_meta) if icy else 64 * 1024
                chunk = f.read(min(64 * 1024, want))
                if chunk:
                    self.wfile.write(chunk)
                    last_growth = time.time()
                    if icy:
                        since_meta += len(chunk)
                        if since_meta == ICY_METAINT:
                            self.wfile.write(icy_block(None if sent_title else title))
                            sent_title = True
                            since_meta = 0
                    continue
                if self.cache.is_ready(vid):  # fully cached and fully sent
                    break
                if time.time() - last_growth > STALL_TIMEOUT:
                    log.warning("stall while serving %s", vid)
                    break
                time.sleep(0.2)  # wait for the download to append more


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
    server.cache = TrackCache()
    log.info("ytm-winamp bridge listening on http://127.0.0.1:%d (cache: %s)",
             port, server.cache.dir)
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
