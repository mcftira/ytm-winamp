"""Extra offline unit tests: pure seams of bins, charts, era, installer, winamp."""
import io
import json
import tempfile
import time
import zipfile
from pathlib import Path

import pytest

from ytm_winamp import bins, charts, era, installer
from ytm_winamp.resolver import Track
from ytm_winamp.winamp import write_playlist


def _ffmpeg_zip(payload: bytes) -> bytes:
    """A tiny in-memory zip shaped like the gyan.dev ffmpeg essentials build."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ffmpeg-7.1-essentials_build/doc/readme.txt", b"docs")
        zf.writestr("ffmpeg-7.1-essentials_build/bin/ffplay.exe", b"decoy")
        zf.writestr("ffmpeg-7.1-essentials_build/bin/ffmpeg.exe", payload)
    return buf.getvalue()


def test_download_tool_extracts_ffmpeg_from_zip(monkeypatch, tmp_path):
    payload = b"fake ffmpeg binary"
    seen_urls = []

    def fake_download(url, dest):
        seen_urls.append(url)
        dest.write_bytes(_ffmpeg_zip(payload))

    monkeypatch.setattr(bins, "_download", fake_download)
    dest = bins.download_tool("ffmpeg", progress=lambda msg: None,
                              dest_dir=tmp_path)
    assert seen_urls == [bins.FFMPEG_URL]
    assert dest == tmp_path / "ffmpeg.exe"
    assert dest.read_bytes() == payload
    # the intermediate zip in the temp dir is cleaned up
    assert not (Path(tempfile.gettempdir()) / "ytm-winamp-ffmpeg.zip").exists()


def test_download_tool_rejects_unknown_tool(tmp_path):
    with pytest.raises(ValueError, match="no portable build"):
        bins.download_tool("curl", progress=lambda msg: None, dest_dir=tmp_path)


def test_clean_strips_nested_refs():
    assert charts._clean("Sandstorm[1][note 2]") == "Sandstorm"
    assert charts._clean("Blue (Da Ba Dee)[12][NOTE 3]") == "Blue (Da Ba Dee)"


def test_clean_normalizes_non_breaking_spaces():
    assert charts._clean("Daft\u00a0Punk\u00a0-\u00a0One\u00a0More\u00a0Time") == "Daft Punk - One More Time"
    assert charts._clean("\u00a0\u00a0Believe\u00a0") == "Believe"


def test_clean_strips_mixed_quotes_keeps_inner_apostrophes():
    assert charts._clean('„"Don\'t Stop"“') == "Don't Stop"
    assert charts._clean("''It's My Life''") == "It's My Life"
    assert charts._clean('„Cotton Eye Joe"') == "Cotton Eye Joe"


def test_load_cache_drops_expired_entries(tmp_path):
    now = time.time()
    cache_file = tmp_path / "era_cache.json"
    cache_file.write_text(json.dumps({
        "fresh": {"video_id": "aaaaaaaaaaa", "title": "New", "resolved_at": now},
        "stale": {"video_id": "bbbbbbbbbbb", "title": "Old",
                  "resolved_at": now - era.CACHE_TTL - 60},
        "no_timestamp": {"video_id": "ccccccccccc", "title": "Ancient"},
    }), encoding="utf-8")
    assert set(era._load_cache(cache_file)) == {"fresh"}


def test_load_cache_missing_file(tmp_path):
    assert era._load_cache(tmp_path / "nope.json") == {}


def test_load_cache_corrupt_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert era._load_cache(bad) == {}


class _FirstKRandom:
    """Deterministic rng for select_queries: always picks the first k items."""

    def sample(self, pool, k):
        return list(pool)[:k]

    def shuffle(self, items):
        pass


@pytest.mark.xfail(
    reason="era.select_queries does not dedup local queries against global "
           "TRACKS yet (era.py is owned by another agent); drop this marker "
           "once the fix lands",
    strict=False)
def test_select_queries_dedups_local_against_global(monkeypatch):
    local = [era.TRACKS[0]] + [f"Local Artist{i} - Song{i}" for i in range(50)]
    monkeypatch.setattr(charts, "detect_country", lambda: ("DE", "Germany"))
    monkeypatch.setattr(charts, "fetch_chart_queries",
                        lambda cc, name=None: local)
    queries, note = era.select_queries(10, shuffle=False, rng=_FirstKRandom())
    assert queries.count(era.TRACKS[0]) == 1
    assert len(queries) == len(set(queries))
    assert note == "mixed with Germany number-one hits"


def test_ensure_skin_idempotent_replaces_existing(tmp_path):
    ini = tmp_path / "winamp.ini"
    ini.write_text("[Winamp]\nuid=x\nskin=Winamp Classic\n[Other]\nfoo=1\n",
                   encoding="utf-8")
    msg1 = installer.ensure_skin("Winamp Modern", ini)
    first = ini.read_text(encoding="utf-8")
    msg2 = installer.ensure_skin("Winamp Modern", ini)
    second = ini.read_text(encoding="utf-8")
    assert first == second
    assert msg1 == msg2
    assert second.count("skin=") == 1
    assert "uid=x" in second and "foo=1" in second


def test_ensure_skin_idempotent_insert_path(tmp_path):
    ini = tmp_path / "winamp.ini"
    ini.write_text("[Winamp]\nuid=x\n", encoding="utf-8")
    msg1 = installer.ensure_skin("Winamp Modern", ini)
    first = ini.read_text(encoding="utf-8")
    msg2 = installer.ensure_skin("Winamp Modern", ini)
    second = ini.read_text(encoding="utf-8")
    assert first == second
    assert msg1 == msg2
    assert second.splitlines()[1] == "skin=Winamp Modern"
    assert second.count("skin=") == 1


def test_write_playlist_roundtrip_commas_and_unicode():
    tracks = [
        Track("aaaaaaaaaaa", "Cambodia, Pt. 2", "Kim Wilde", 221),
        Track("bbbbbbbbbbb", "Híd a folyót", "T.N.T.", 190),
        Track("ccccccccccc", "Dragostea Din Tei (Ma-ia-hii)", "O-Zone"),
    ]
    path = write_playlist(tracks, port=8797)
    try:
        text = path.read_bytes().decode("utf-8")  # must be valid utf-8
        lines = text.splitlines()
        assert lines[0] == "#EXTM3U"
        parsed = []
        for i in range(1, len(lines), 2):
            duration, _, title = lines[i].partition(",")  # first comma only
            parsed.append((int(duration.removeprefix("#EXTINF:")), title,
                           lines[i + 1]))
        assert [(d, t) for d, t, _ in parsed] == [
            (221, "Kim Wilde - Cambodia, Pt. 2"),
            (190, "T.N.T. - Híd a folyót"),
            (-1, "O-Zone - Dragostea Din Tei (Ma-ia-hii)"),
        ]
        assert [url for _, _, url in parsed] == [
            f"http://127.0.0.1:8797/stream/{t.video_id}.mp3" for t in tracks
        ]
    finally:
        path.unlink(missing_ok=True)
