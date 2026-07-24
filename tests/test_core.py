"""Offline unit tests for ytm-winamp core helpers (no network, no Winamp)."""
import os

import pytest

from ytm_winamp import charts, era, installer, server
from ytm_winamp.resolver import DownloadError, Track, is_url, liked_songs
from ytm_winamp.server import TrackCache, icy_block
from ytm_winamp.winamp import write_playlist

CHART_HTML = """
<html><body>
<table class="wikitable">
<tr><th>Issue date</th><th>Song</th><th>Artist</th><th>Ref.</th></tr>
<tr><td>5 January</td><td>"It's Like That"</td><td>Run-D.M.C.</td><td>[3]</td></tr>
<tr><td>12 January</td><td>[5]</td><td>[6]</td><td>[7]</td></tr>
<tr><td>19 January</td><td>"Believe" †</td><td>Cher</td><td>[8]</td></tr>
</table>
<table class="wikitable">
<tr><th>Foo</th><th>Bar</th></tr>
<tr><td>1</td><td>2</td></tr>
</table>
</body></html>
"""


def test_parse_chart_page_forward_fills_and_dedups():
    pairs = charts.parse_chart_page(CHART_HTML)
    assert pairs == [("It's Like That", "Run-D.M.C."), ("Believe", "Cher")]


def test_chart_clean_strips_refs_and_quotes():
    assert charts._clean('" Believe " [12] †') == "Believe"
    assert charts._clean("[5]") == ""


def test_select_queries_global_only():
    import random

    queries, note = era.select_queries(20, shuffle=True, local=False,
                                       rng=random.Random(42))
    assert len(queries) == 20
    assert note == "global hits only"


def test_select_queries_mixes_local_hits(monkeypatch):
    import random

    local = [f"Local Artist{i} - Song{i}" for i in range(50)]
    monkeypatch.setattr(charts, "detect_country", lambda: ("DE", "Germany"))
    monkeypatch.setattr(charts, "fetch_chart_queries",
                        lambda cc, name=None: local)
    queries, note = era.select_queries(20, shuffle=True, rng=random.Random(42))
    assert note == "mixed with Germany number-one hits"
    assert len(queries) == 20
    n_local = sum(1 for q in queries if q.startswith("Local Artist"))
    assert n_local == round(20 * era.LOCAL_SHARE)


def test_select_queries_graceful_when_country_unknown(monkeypatch):
    import random

    monkeypatch.setattr(charts, "detect_country", lambda: (None, None))
    queries, note = era.select_queries(10, shuffle=True, rng=random.Random(1))
    assert len(queries) == 10
    assert "global hits only" in note


SLAGER_HTML = """
<html><body><table>
<tr>
  <td class="no_sor">2.</td>
  <td class="hetek_szama_sor">42</td>
  <td class="csucs_sor">1</td>
  <td class="lemez_sor2"><span class="eloado">Dido</span><br />White Flag<br />
    <span class="kiado_sor">(BMG)</span></td>
</tr>
<tr>
  <td class="no_sor">5.</td>
  <td class="hetek_szama_sor">39</td>
  <td class="csucs_sor">2</td>
  <td class="lemez_sor2"><span class="eloado">T.N.T.</span><br />Híd a folyót<br />
    <span class="kiado_sor">(Magneoton)</span></td>
</tr>
</table></body></html>
"""


def test_parse_slagerlistak_page():
    pairs = charts.parse_slagerlistak_page(SLAGER_HTML)
    assert pairs == [("White Flag", "Dido"), ("Híd a folyót", "T.N.T.")]


def test_ensure_skin_updates_existing(tmp_path):
    ini = tmp_path / "winamp.ini"
    ini.write_text("[Winamp]\nuid=x\nskin=Winamp Classic\n[Other]\nfoo=1\n",
                   encoding="utf-8")
    installer.ensure_skin("Winamp Modern", ini)
    text = ini.read_text(encoding="utf-8")
    assert "skin=Winamp Modern" in text
    assert "Classic" not in text
    assert "uid=x" in text and "foo=1" in text


def test_ensure_skin_inserts_when_missing(tmp_path):
    ini = tmp_path / "winamp.ini"
    ini.write_text("[Winamp]\nuid=x\n", encoding="utf-8")
    installer.ensure_skin("Winamp Modern", ini)
    assert ini.read_text(encoding="utf-8").splitlines()[1] == "skin=Winamp Modern"


def test_ensure_skin_without_ini(tmp_path):
    msg = installer.ensure_skin("Winamp Modern", tmp_path / "nope.ini")
    assert "no winamp.ini yet" in msg


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
