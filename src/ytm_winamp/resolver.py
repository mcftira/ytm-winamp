"""Resolve search queries and YouTube / YouTube Music URLs to track metadata."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

__all__ = ["Track", "DownloadError", "is_url", "search", "resolve",
           "search_playlists", "playlist_tracks"]


@dataclass
class Track:
    video_id: str
    title: str
    uploader: str = ""
    duration: int = 0  # seconds; 0 means unknown

    @property
    def watch_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def display(self) -> str:
        return f"{self.uploader} - {self.title}" if self.uploader else self.title


_YDL_BASE = {"quiet": True, "no_warnings": True, "skip_download": True}


def _to_track(entry: dict) -> Track:
    return Track(
        video_id=entry["id"],
        title=entry.get("title") or entry["id"],
        uploader=entry.get("uploader") or entry.get("channel") or "",
        duration=int(entry.get("duration") or 0),
    )


def is_url(text: str) -> bool:
    try:
        return urlparse(text).scheme in ("http", "https")
    except ValueError:
        return False


def search(query: str, count: int = 5) -> list[Track]:
    """Return the top ``count`` YouTube search results for ``query``."""
    opts = {**_YDL_BASE, "extract_flat": True, "noplaylist": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{count}:{query}", download=False)
    return [_to_track(e) for e in (info.get("entries") or []) if e]


def resolve(url: str) -> list[Track]:
    """Resolve a single video URL or a playlist URL to a list of tracks."""
    with YoutubeDL({**_YDL_BASE, "extract_flat": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or []
    if entries:
        return [_to_track(e) for e in entries if e]
    return [_to_track(info)]


DEFAULT_AUTH_PATH = Path.home() / ".ytm-winamp" / "ytmusic.json"

_AUTH_HELP = """\
YouTube Music auth not found at {path}.
One-time setup — run ONE of these and move the resulting file to {path}:
  ytmusicapi oauth     (recommended; needs a Google Cloud OAuth client,
                        see ytmusicapi.readthedocs.io)
  ytmusicapi browser   (paste request headers copied from music.youtube.com)
"""


def liked_songs(auth: str | None = None, limit: int = 250) -> list[Track]:
    """Fetch the user's YouTube Music liked songs (requires ytmusicapi auth)."""
    try:
        from ytmusicapi import YTMusic
    except ImportError as exc:
        raise DownloadError(
            "ytmusicapi is not installed; run: pip install ytmusicapi"
        ) from exc
    path = Path(auth) if auth else DEFAULT_AUTH_PATH
    if not path.exists():
        raise DownloadError(_AUTH_HELP.format(path=path))
    resp = YTMusic(str(path)).get_liked_songs(limit=limit)
    tracks = []
    for e in resp.get("tracks", []):
        artists = ", ".join(a.get("name", "") for a in e.get("artists") or [])
        tracks.append(Track(
            video_id=e["videoId"],
            title=e.get("title") or e["videoId"],
            uploader=artists,
            duration=int(e.get("duration_seconds") or 0),
        ))
    return tracks


def _public_ytmusic():
    """Return an unauthenticated YTMusic client (public data only)."""
    try:
        from ytmusicapi import YTMusic
    except ImportError as exc:
        raise DownloadError(
            "ytmusicapi is not installed; run: pip install ytmusicapi"
        ) from exc
    return YTMusic()


def _owner(author) -> str:
    # ytmusicapi returns the author either as a string or a list of dicts
    if isinstance(author, list):
        return ", ".join(a.get("name", "") for a in author)
    return author or ""


def search_playlists(query: str, count: int = 5) -> list[dict]:
    """Search public YouTube Music playlists by name (no auth needed).

    Returns up to ``count`` dicts with keys: id, name, owner, track_count
    (track_count may be None when YouTube does not report it).
    """
    yt = _public_ytmusic()
    try:
        results = yt.search(query, filter="playlists", limit=count) or []
    except Exception as exc:
        raise DownloadError(f"playlist search failed: {exc}") from exc
    candidates = []
    for r in results:
        browse_id = r.get("browseId") or ""
        # search results carry the playlist id with a "VL" prefix
        pid = browse_id[2:] if browse_id.startswith("VL") else browse_id
        if not pid:
            continue
        candidates.append({
            "id": pid,
            "name": r.get("title") or pid,
            "owner": _owner(r.get("author")),
            "track_count": r.get("itemCount"),
        })
        if len(candidates) >= count:
            break
    return candidates


def playlist_tracks(playlist_id: str, limit: int = 50) -> list[Track]:
    """Return up to ``limit`` tracks of a public playlist (no auth needed)."""
    yt = _public_ytmusic()
    try:
        resp = yt.get_playlist(playlist_id, limit=limit)
    except Exception as exc:
        raise DownloadError(f"could not read playlist: {exc}") from exc
    tracks = []
    # get_playlist's limit is a batch minimum, so slice to the real cap
    for e in (resp.get("tracks") or [])[:limit]:
        vid = e.get("videoId")
        if not vid:
            continue  # unavailable/deleted entries have no videoId
        artists = ", ".join(a.get("name", "") for a in e.get("artists") or [])
        tracks.append(Track(
            video_id=vid,
            title=e.get("title") or vid,
            uploader=artists,
            duration=int(e.get("duration_seconds") or 0),
        ))
    return tracks
