"""Locate or fetch the external binaries ytm-winamp needs (yt-dlp, ffmpeg).

Lookup order: PATH first, then the portable bin dir under the user's home.
`setup` downloads the portable builds when neither is available, so end
users need nothing installed beyond the ytm-winamp exe and Winamp itself.
"""
from __future__ import annotations

import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path

LOCAL_BIN = Path.home() / ".ytm-winamp" / "bin"

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
# gyan.dev "release essentials": a stable URL for the latest static ffmpeg
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

USER_AGENT = "ytm-winamp (+https://github.com/mcftira/ytm-winamp)"


class ToolNotFound(RuntimeError):
    pass


def local_tool_path(name: str) -> Path:
    return LOCAL_BIN / f"{name}.exe"


def find_tool(name: str) -> str:
    """Return the path to a tool on PATH or in the portable bin dir."""
    on_path = shutil.which(name)
    if on_path:
        return on_path
    local = local_tool_path(name)
    if local.is_file():
        return str(local)
    raise ToolNotFound(
        f"{name!r} not found on PATH or in {LOCAL_BIN}; run: ytm-winamp setup"
    )


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(resp.read())
    tmp.replace(dest)


def download_tool(name: str, progress=print) -> Path:
    """Download a portable build of a tool into the local bin dir."""
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    dest = local_tool_path(name)
    if name == "yt-dlp":
        progress(f"  downloading yt-dlp ({YTDLP_URL})")
        _download(YTDLP_URL, dest)
    elif name == "ffmpeg":
        progress(f"  downloading ffmpeg essentials ({FFMPEG_URL}); this is ~50 MB")
        zip_path = Path(tempfile.gettempdir()) / "ytm-winamp-ffmpeg.zip"
        _download(FFMPEG_URL, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            member = next(m for m in zf.namelist()
                          if m.endswith("bin/ffmpeg.exe"))
            with zf.open(member) as src:
                dest.write_bytes(src.read())
        zip_path.unlink(missing_ok=True)
    else:
        raise ValueError(f"no portable build known for {name!r}")
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR)
    progress(f"  {name}: saved to {dest}")
    return dest
