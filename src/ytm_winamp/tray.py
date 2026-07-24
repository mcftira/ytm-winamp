"""Windows system-tray companion: an icon with playback controls for Winamp.

The ctypes helpers (find the Winamp window, send IPC commands, read the
now-playing title) are pure stdlib and stay importable without a display;
only ``build_menu``/``main`` below need pystray + Pillow and a desktop.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import sys
import tempfile
import threading
from pathlib import Path

WM_COMMAND = 0x0111
WM_USER = 0x0400
WINAMP_CLASS = "Winamp v1.x"

# WM_COMMAND ids handled by classic Winamp's main window
CMD_PREVIOUS = 40044
CMD_PLAY = 40045
CMD_PAUSE = 40046
CMD_STOP = 40047
CMD_NEXT = 40048
# WM_USER query: 1 = playing, 3 = paused, 0 = stopped
IPC_ISPLAYING = 104

STATE_STOPPED = 0
STATE_PLAYING = 1
STATE_PAUSED = 3
STATE_NO_WINAMP = -1

BRIDGE_LOG = Path(tempfile.gettempdir()) / "ytm-winamp-bridge.log"

_U32 = None  # cached user32 handle; tests swap in a fake


def _user32():
    """Load user32 once, with 64-bit-safe prototypes (HWND is pointer-sized)."""
    global _U32
    if _U32 is None:
        u32 = ctypes.windll.user32
        u32.FindWindowW.restype = ctypes.wintypes.HWND
        u32.FindWindowW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR]
        u32.SendMessageW.restype = ctypes.wintypes.LPARAM
        u32.SendMessageW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT,
                                     ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
        u32.GetWindowTextLengthW.restype = ctypes.c_int
        u32.GetWindowTextLengthW.argtypes = [ctypes.wintypes.HWND]
        u32.GetWindowTextW.restype = ctypes.c_int
        u32.GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR,
                                       ctypes.c_int]
        _U32 = u32
    return _U32


def find_winamp_window() -> int:
    """HWND of the Winamp main window, or 0 when Winamp is not running."""
    return _user32().FindWindowW(WINAMP_CLASS, None) or 0


def send_command(command: int, hwnd: int | None = None) -> bool:
    """Post a WM_COMMAND to Winamp; False when no Winamp window exists."""
    hwnd = find_winamp_window() if hwnd is None else hwnd
    if not hwnd:
        return False
    _user32().SendMessageW(hwnd, WM_COMMAND, command, 0)
    return True


def previous_track(hwnd: int | None = None) -> bool:
    return send_command(CMD_PREVIOUS, hwnd)


def play(hwnd: int | None = None) -> bool:
    return send_command(CMD_PLAY, hwnd)


def pause(hwnd: int | None = None) -> bool:
    return send_command(CMD_PAUSE, hwnd)


def stop(hwnd: int | None = None) -> bool:
    return send_command(CMD_STOP, hwnd)


def next_track(hwnd: int | None = None) -> bool:
    return send_command(CMD_NEXT, hwnd)


def play_state(hwnd: int | None = None) -> int:
    """STATE_PLAYING/PAUSED/STOPPED, or STATE_NO_WINAMP when not running."""
    hwnd = find_winamp_window() if hwnd is None else hwnd
    if not hwnd:
        return STATE_NO_WINAMP
    return _user32().SendMessageW(hwnd, WM_USER, 0, IPC_ISPLAYING)


def toggle_playback(hwnd: int | None = None) -> bool:
    """Pause while playing; play (resume/start) otherwise."""
    if play_state(hwnd) == STATE_PLAYING:
        return pause(hwnd)
    return play(hwnd)  # paused resumes, stopped starts: both via CMD_PLAY


def window_text(hwnd: int) -> str:
    """The raw title of a window, '' when the handle is invalid."""
    length = _user32().GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32().GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def parse_window_title(text: str) -> str:
    """Now-playing track from a Winamp window title, '' when idle.

    Handles '12. Artist - Title - Winamp [Paused]' and bare 'Winamp'.
    """
    title = text.strip()
    for suffix in (" [Paused]", " [Stopped]"):
        if title.endswith(suffix):
            title = title[: -len(suffix)]
    if title.endswith(" - Winamp"):
        title = title[: -len(" - Winamp")]
    elif title == "Winamp":
        return ""
    if ". " in title:  # strip the playlist position prefix
        head, rest = title.split(". ", 1)
        if head.isdigit():
            title = rest
    return title


def now_playing(hwnd: int | None = None) -> str:
    """Current Winamp track title, '' when stopped or Winamp is not running."""
    hwnd = find_winamp_window() if hwnd is None else hwnd
    if not hwnd:
        return ""
    return parse_window_title(window_text(hwnd))


def now_playing_text() -> str:
    """Menu label for the read-only 'now playing' entry."""
    title = now_playing()
    return f"Now playing: {title}" if title else "Now playing: (nothing)"


def icon_path() -> Path:
    """docs/icon.png, honouring YTM_WINAMP_ICON and frozen (PyInstaller) runs."""
    override = os.environ.get("YTM_WINAMP_ICON")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        bundled = Path(getattr(sys, "_MEIPASS",
                                 Path(sys.executable).parent)) / "docs" / "icon.png"
        if bundled.is_file():
            return bundled
    return Path(__file__).resolve().parents[2] / "docs" / "icon.png"


def load_icon_image(path: Path | None = None):
    from PIL import Image

    return Image.open(path or icon_path())


def launch_era_radio(count: int = 25, port: int | None = None) -> threading.Thread:
    """Resolve the era queue and hand it to Winamp, off the tray thread."""
    def _run() -> None:
        try:
            from . import era, winamp

            tracks, _note = era.era_tracks(count=count)
            if tracks:
                winamp.play(tracks, port=port or winamp.DEFAULT_PORT)
        except Exception:
            pass  # network/resolution failures must never kill the tray icon

    thread = threading.Thread(target=_run, name="ytm-era-radio", daemon=True)
    thread.start()
    return thread


def open_bridge_log() -> Path:
    """Open the bridge log with the default viewer; create it when missing."""
    BRIDGE_LOG.touch(exist_ok=True)
    os.startfile(BRIDGE_LOG)
    return BRIDGE_LOG


def build_menu():
    """The right-click menu; 'Now playing' and Play/Pause refresh on open."""
    from pystray import Menu, MenuItem

    return Menu(
        MenuItem(lambda item: now_playing_text(), None, enabled=False),
        MenuItem(lambda item: "Pause" if play_state() == STATE_PLAYING else "Play",
                 lambda icon, item: toggle_playback()),
        MenuItem("Previous", lambda icon, item: previous_track()),
        MenuItem("Next", lambda icon, item: next_track()),
        Menu.SEPARATOR,
        MenuItem("Era radio", lambda icon, item: launch_era_radio()),
        MenuItem("Open bridge log", lambda icon, item: open_bridge_log()),
        Menu.SEPARATOR,
        MenuItem("Quit", lambda icon, item: icon.stop()),
    )


def main() -> int:
    """Show the tray icon and run its event loop until Quit."""
    import pystray

    icon = pystray.Icon("ytm-winamp", load_icon_image(), "ytm-winamp", build_menu())
    icon.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
