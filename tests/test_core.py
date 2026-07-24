"""Offline unit tests for ytm-winamp core helpers (no network, no Winamp)."""
from ytm_winamp.resolver import Track, is_url
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
