"""Winamp integration: locate the player, manage the bridge, enqueue playlists."""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from .resolver import Track
from .server import DEFAULT_PORT

_WINAMP_CANDIDATES = [
    r"C:\Program Files (x86)\Winamp\winamp.exe",
    r"C:\Program Files\Winamp\winamp.exe",
]


class WinampError(RuntimeError):
    pass


def find_winamp() -> Path:
    override = os.environ.get("YTM_WINAMP_EXE")
    candidates = [override] if override else _WINAMP_CANDIDATES
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise WinampError("winamp.exe not found; set YTM_WINAMP_EXE to its full path")


def server_up(port: int = DEFAULT_PORT) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def _server_argv(port: int) -> list[str]:
    """How to launch the bridge process, in frozen (PyInstaller) form or not."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "serve", "--port", str(port)]
    return [sys.executable, "-m", "ytm_winamp.server", "--port", str(port)]


def ensure_server(port: int = DEFAULT_PORT) -> None:
    """Start the bridge as a detached background process unless already running."""
    if server_up(port):
        return
    log_path = Path(tempfile.gettempdir()) / "ytm-winamp-bridge.log"
    log_file = open(log_path, "ab")
    flags = (
        subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.CREATE_NO_WINDOW
    )
    subprocess.Popen(
        _server_argv(port),
        stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT,
        creationflags=flags, close_fds=True,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        if server_up(port):
            return
        time.sleep(0.3)
    raise WinampError(f"bridge server failed to start; see {log_path}")


def write_playlist(tracks: list[Track], port: int = DEFAULT_PORT) -> Path:
    lines = ["#EXTM3U"]
    for t in tracks:
        duration = t.duration if t.duration > 0 else -1
        lines.append(f"#EXTINF:{duration},{t.display}")
        lines.append(f"http://127.0.0.1:{port}/stream/{t.video_id}.mp3")
    fd, name = tempfile.mkstemp(prefix="ytm-winamp-", suffix=".m3u8")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return Path(name)


def prefetch(tracks: list[Track], port: int = DEFAULT_PORT) -> None:
    """Ask the bridge to start downloading tracks; best-effort."""
    # very long videos (mixes, compilations) are fetched on demand instead:
    # background-prefetching one would starve the tracks behind it
    payload = {
        "vids": [t.video_id for t in tracks if not t.duration or t.duration <= 900],
        "titles": {t.video_id: t.display for t in tracks},
    }
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/prefetch", body=json.dumps(payload),
                     headers={"Content-Type": "application/json"})
        conn.getresponse().read()
        conn.close()
    except OSError:
        pass


_WM_USER = 0x0400
_IPC_GETLISTLENGTH = 124


def _find_winamp_window() -> int:
    """Handle of Winamp's IPC window, or 0 when Winamp is not running."""
    import ctypes

    return ctypes.windll.user32.FindWindowW("Winamp v1.x", None) or 0


def _playlist_length(hwnd: int) -> int:
    import ctypes

    return int(ctypes.windll.user32.SendMessageW(hwnd, _WM_USER, 0, _IPC_GETLISTLENGTH))


def play(tracks: list[Track], port: int = DEFAULT_PORT) -> None:
    if not tracks:
        raise WinampError("nothing to play")
    ensure_server(port)
    prefetch(tracks, port)
    playlist = write_playlist(tracks, port)
    exe = find_winamp()
    was_running = _find_winamp_window() != 0
    subprocess.Popen([str(exe), str(playlist)])
    if not was_running:
        _await_playlist_load(exe, playlist, expected=len(tracks))


def _await_playlist_load(exe: Path, playlist: Path, expected: int) -> None:
    """Verify a freshly launched Winamp actually loaded the playlist.

    A never-before-run Winamp spends a while in first-run initialization and
    silently drops the command-line playlist handoff; retry the launch once
    when the playlist still has not shown up after a grace period.
    """
    deadline = time.time() + 30
    while time.time() < deadline:
        hwnd = _find_winamp_window()
        if hwnd and _playlist_length(hwnd) >= expected:
            return
        time.sleep(2)
    hwnd = _find_winamp_window()
    if not hwnd or _playlist_length(hwnd) < expected:
        subprocess.Popen([str(exe), str(playlist)])
