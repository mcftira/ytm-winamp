"""First-run onboarding: install Winamp and dependencies, set the theme.

The goal is that a new user can go from nothing to a playing Winamp with:

    pipx install .
    ytm-winamp setup
    ytm-winamp

Everything here is idempotent: whatever is already present is left alone.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import winamp as _winamp

DEFAULT_SKIN = "Winamp Modern"

# external tools, mapped to their winget package ids
_TOOLS = [
    ("yt-dlp", "yt-dlp.yt-dlp"),
    ("ffmpeg", "Gyan.FFmpeg"),
]


def _have_winget() -> bool:
    return shutil.which("winget") is not None


def _winget_install(package_id: str) -> bool:
    """Install a package via winget; returns True on success."""
    print(f"  installing {package_id} via winget (a UAC prompt may appear)...")
    proc = subprocess.run(
        ["winget", "install", "--id", package_id, "-e",
         "--accept-package-agreements", "--accept-source-agreements"],
    )
    return proc.returncode == 0


def ensure_tool(name: str, winget_id: str) -> bool:
    if shutil.which(name):
        print(f"  {name}: found")
        return True
    if not _have_winget():
        print(f"  {name}: MISSING and winget is unavailable;")
        print(f"    install it manually and make sure it is on PATH")
        return False
    if _winget_install(winget_id) and shutil.which(name):
        print(f"  {name}: installed")
        return True
    # winget may have installed it for a future PATH; warn but continue
    print(f"  {name}: install attempted; if it is still not found, "
          f"open a new terminal so PATH updates")
    return shutil.which(name) is not None


def ensure_winamp() -> bool:
    try:
        path = _winamp.find_winamp()
        print(f"  Winamp: found at {path}")
        return True
    except _winamp.WinampError:
        pass
    if not _have_winget():
        print("  Winamp: MISSING and winget is unavailable;")
        print("    install it from https://www.winamp.com/player/")
        return False
    if _winget_install("Winamp.Winamp"):
        try:
            path = _winamp.find_winamp()
            print(f"  Winamp: installed at {path}")
            return True
        except _winamp.WinampError:
            pass
    print("  Winamp: install attempted; if it is still not found, set "
          "YTM_WINAMP_EXE to the winamp.exe path")
    return False


def winamp_ini_path() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "Winamp" / "winamp.ini"


def ensure_skin(skin: str = DEFAULT_SKIN, ini_path: Path | None = None) -> str:
    """Make ``skin`` the configured Winamp theme in winamp.ini.

    Only touches the file when it already exists (a fresh Winamp defaults
    to the modern skin anyway). Returns a short status for display.
    """
    path = ini_path or winamp_ini_path()
    if not path.exists():
        return f"skin: {skin} (Winamp default; no winamp.ini yet)"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    had_skin = any(l.startswith("skin=") for l in lines)
    if had_skin:
        lines = [f"skin={skin}" if l.startswith("skin=") else l for l in lines]
    else:  # insert into the [Winamp] section
        for i, line in enumerate(lines):
            if line.strip().lower() == "[winamp]":
                lines.insert(i + 1, f"skin={skin}")
                break
        else:
            lines.append(f"[Winamp]\nskin={skin}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"skin: set to {skin} in {path.name}"


def run_setup() -> int:
    print("ytm-winamp setup")
    ok = True
    ok = ensure_winamp() and ok
    for name, winget_id in _TOOLS:
        ok = ensure_tool(name, winget_id) and ok
    print(" ", ensure_skin())
    if ok:
        print("\nall set — start the era radio with:  ytm-winamp")
        return 0
    print("\nsetup finished with warnings; see above, then run:  ytm-winamp")
    return 1
