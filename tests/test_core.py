"""Offline unit tests for ytm-winamp core helpers (no network, no Winamp)."""
import os

import pytest

from ytm_winamp import server
from ytm_winamp.resolver import DownloadError, Track, is_url, liked_songs
from ytm_winamp.server import TrackCache, icy_block
from ytm_winamp.winamp import write_playlist


def test_track_display():
    t = Track("dQw4w9WgXcQ", "Cheri Cheri Lady", "Modern Talking", 238)
    assert t.display == "Modern Talking - Cheri Cheri Lady"
    assert t.watch_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_track_display_without_uploader():
    assert Track("abc", "Just A Title").display == "Just A Title"


def test_is_url():
    assert is_url("https://music.youtube.com/watch?v=abc")
    assert is_url("http://youtu.be/abc")
    assert not is_url("cheri cheri lady")


def test_write_playlist():
    tracks = [
        Track("abcdefghijk", "Song One", "Artist", 200),
        Track("klmnopqrstu", "Song Two"),
    ]
    path = write_playlist(tracks, port=8797)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("#EXTM3U")
    assert "#EXTINF:200,Artist - Song One" in text
    assert "#EXTINF:-1,Song Two" in text
    assert "http://127.0.0.1:8797/stream/abcdefghijk.mp3" in text
    assert "http://127.0.0.1:8797/stream/klmnopqrstu.mp3" in text


def _make_ready(cache: TrackCache, vid: str, mtime: float = 0.0) -> None:
    p = cache.mp3_path(vid)
    p.write_bytes(b"mp3data")
    if mtime:
        os.utime(p, (mtime, mtime))
    cache.done_path(vid).touch()


def test_cache_ready_requires_done_marker(tmp_path):
    c = TrackCache(tmp_path, start_worker=False)
    vid = "abcdefghijk"
    assert not c.is_ready(vid)
    c.mp3_path(vid).write_bytes(b"partial")
    assert not c.is_ready(vid)  # download in progress: mp3 but no marker
    c.done_path(vid).touch()
    assert c.is_ready(vid)


def test_cache_prefetch_skips_ready_and_clears_failures(tmp_path):
    import time

    c = TrackCache(tmp_path, start_worker=False)
    _make_ready(c, "aaaaaaaaaaa")
    c._failed["bbbbbbbbbbb"] = time.time()
    assert c.recently_failed("bbbbbbbbbbb")
    c.prefetch(["aaaaaaaaaaa", "bbbbbbbbbbb"])
    assert c._queue == ["bbbbbbbbbbb"]  # ready track skipped
    assert not c.recently_failed("bbbbbbbbbbb")  # retry window cleared


def test_cache_ensure_jumps_queue_front(tmp_path):
    c = TrackCache(tmp_path, start_worker=False)
    c.prefetch(["aaaaaaaaaaa", "bbbbbbbbbbb"])
    c.ensure("bbbbbbbbbbb")
    assert c._queue[0] == "bbbbbbbbbbb"


def test_cache_in_progress(tmp_path):
    c = TrackCache(tmp_path, start_worker=False)
    assert not c.in_progress("aaaaaaaaaaa")
    c.prefetch(["aaaaaaaaaaa"])
    assert c.in_progress("aaaaaaaaaaa")


def test_cache_eviction_keeps_newest(tmp_path):
    c = TrackCache(tmp_path, start_worker=False)
    for i in range(server.MAX_CACHE_FILES + 2):
        _make_ready(c, f"vid{i:08d}"[:11], mtime=1000 + i)
    c._evict()
    remaining = sorted(f.stem for f in tmp_path.glob("*.mp3"))
    assert len(remaining) == server.MAX_CACHE_FILES
    assert "vid00000000" not in remaining
    assert "vid00000001" not in remaining


def test_liked_songs_missing_auth_file(tmp_path):
    with pytest.raises(DownloadError, match="auth not found"):
        liked_songs(auth=str(tmp_path / "nope.json"))


def test_icy_block_empty():
    assert icy_block(None) == b"\x00"


def test_icy_block_title():
    block = icy_block("Artist - Title")
    assert len(block) % 16 == 1  # 1 length byte + 16-byte-aligned payload
    assert block[0] == (len(block) - 1) // 16
    assert b"StreamTitle='Artist - Title';" in block


def test_cache_titles(tmp_path):
    c = TrackCache(tmp_path, start_worker=False)
    assert c.title_for("abc") == "abc"  # falls back to the video id
    c.set_titles({"abc": "A - B"})
    assert c.title_for("abc") == "A - B"
