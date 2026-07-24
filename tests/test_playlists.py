"""Offline unit tests for public playlist radio (no network, no Winamp)."""
import sys
import types

import pytest

from ytm_winamp import cli, resolver
from ytm_winamp.resolver import DownloadError, Track, playlist_tracks, search_playlists


class FakeYTMusic:
    """Stands in for ytmusicapi.YTMusic; serves canned responses."""

    search_results = []
    playlist = {"tracks": []}
    error = None

    def __init__(self, *args, **kwargs):
        pass

    def search(self, query, filter=None, limit=0):
        if FakeYTMusic.error:
            raise FakeYTMusic.error
        assert filter == "playlists"
        return FakeYTMusic.search_results

    def get_playlist(self, playlist_id, limit=0):
        if FakeYTMusic.error:
            raise FakeYTMusic.error
        return FakeYTMusic.playlist


@pytest.fixture
def fake_ytmusicapi(monkeypatch):
    FakeYTMusic.search_results = []
    FakeYTMusic.playlist = {"tracks": []}
    FakeYTMusic.error = None
    module = types.ModuleType("ytmusicapi")
    module.YTMusic = FakeYTMusic
    monkeypatch.setitem(sys.modules, "ytmusicapi", module)
    return FakeYTMusic


def test_search_playlists_maps_candidates(fake_ytmusicapi):
    fake_ytmusicapi.search_results = [
        {"resultType": "playlist", "browseId": "VLPLabc123",
         "title": "90s Hits", "author": "Redlist", "itemCount": 42},
        {"resultType": "playlist", "browseId": "PLplain",
         "title": "List-author mix",
         "author": [{"name": "DJ One"}, {"name": "DJ Two"}], "itemCount": 7},
    ]
    cands = search_playlists("90s hits", count=5)
    assert cands == [
        {"id": "PLabc123", "name": "90s Hits", "owner": "Redlist",
         "track_count": 42},
        {"id": "PLplain", "name": "List-author mix",
         "owner": "DJ One, DJ Two", "track_count": 7},
    ]


def test_search_playlists_respects_count_and_skips_idless(fake_ytmusicapi):
    fake_ytmusicapi.search_results = [
        {"browseId": "", "title": "no id"},
        {"browseId": "VLPLa", "title": "A"},
        {"browseId": "VLPLb", "title": "B"},
    ]
    cands = search_playlists("x", count=1)
    assert [c["id"] for c in cands] == ["PLa"]  # sliced to count, no-id skipped


def test_search_playlists_missing_fields(fake_ytmusicapi):
    fake_ytmusicapi.search_results = [{"browseId": "VLPLx"}]
    (c,) = search_playlists("x")
    assert c == {"id": "PLx", "name": "PLx", "owner": "", "track_count": None}


def test_search_playlists_api_failure_raises_download_error(fake_ytmusicapi):
    fake_ytmusicapi.error = RuntimeError("HTTP 400")
    with pytest.raises(DownloadError, match="playlist search failed"):
        search_playlists("x")


def test_playlist_tracks_maps_and_skips_unavailable(fake_ytmusicapi):
    fake_ytmusicapi.playlist = {"tracks": [
        {"videoId": "vid1", "title": "Creep",
         "artists": [{"name": "Radiohead"}], "duration_seconds": 237},
        {"title": "Deleted video"},  # no videoId -> skipped
        {"videoId": "vid2", "title": None, "artists": None,
         "duration_seconds": None},
    ]}
    tracks = playlist_tracks("PLabc", limit=50)
    assert tracks == [
        Track("vid1", "Creep", "Radiohead", 237),
        Track("vid2", "vid2", "", 0),
    ]


def test_playlist_tracks_caps_at_limit(fake_ytmusicapi):
    # get_playlist's limit is a batch minimum; we slice ourselves
    fake_ytmusicapi.playlist = {"tracks": [
        {"videoId": f"vid{i}"} for i in range(10)
    ]}
    tracks = playlist_tracks("PLabc", limit=3)
    assert [t.video_id for t in tracks] == ["vid0", "vid1", "vid2"]


def test_playlist_tracks_api_failure_raises_download_error(fake_ytmusicapi):
    fake_ytmusicapi.error = RuntimeError("HTTP 404")
    with pytest.raises(DownloadError, match="could not read playlist"):
        playlist_tracks("PLnope")


def test_ytmusicapi_not_installed(monkeypatch):
    # sys.modules entry of None makes `from ytmusicapi import ...` raise
    monkeypatch.setitem(sys.modules, "ytmusicapi", None)
    with pytest.raises(DownloadError, match="ytmusicapi is not installed"):
        search_playlists("x")
    with pytest.raises(DownloadError, match="ytmusicapi is not installed"):
        playlist_tracks("PLx")


def _args(**kw):
    import argparse

    defaults = dict(query=["90s", "hits"], count=50, list=False, port=8797)
    return argparse.Namespace(**{**defaults, **kw})


def test_mix_list_prints_candidates(monkeypatch, capsys):
    monkeypatch.setattr(resolver, "search_playlists", lambda q, count=5: [
        {"id": "PLa", "name": "90s Hits", "owner": "Redlist", "track_count": 42},
        {"id": "PLb", "name": "Mystery Mix", "owner": "", "track_count": None},
    ])
    rc = cli.main(["mix", "90s", "hits", "--list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "1. 90s Hits — Redlist (42 tracks)" in out
    assert "2. Mystery Mix — unknown (? tracks)" in out


def test_mix_no_results_returns_1(monkeypatch, capsys):
    monkeypatch.setattr(resolver, "search_playlists", lambda q, count=5: [])
    rc = cli.main(["mix", "no such playlist"])
    assert rc == 1
    assert "no public playlists found" in capsys.readouterr().err


def test_mix_queues_top_playlist(monkeypatch, capsys):
    monkeypatch.setattr(resolver, "search_playlists", lambda q, count=5: [
        {"id": "PLtop", "name": "Top Mix", "owner": "Someone", "track_count": 9},
        {"id": "PLother", "name": "Other", "owner": "Else", "track_count": 5},
    ])
    seen = {}

    def fake_playlist_tracks(pid, limit=50):
        seen["pid"], seen["limit"] = pid, limit
        return [Track("vid1", "Song", "Artist", 200)]

    played = {}

    def fake_play(tracks, port=0):
        played["tracks"] = tracks

    monkeypatch.setattr(resolver, "playlist_tracks", fake_playlist_tracks)
    monkeypatch.setattr(cli.winamp, "play", fake_play)
    rc = cli.main(["mix", "top", "-n", "10"])
    assert rc == 0
    assert seen == {"pid": "PLtop", "limit": 10}
    assert played["tracks"] == [Track("vid1", "Song", "Artist", 200)]
    assert "playlist: Top Mix by Someone" in capsys.readouterr().err


def test_mix_empty_playlist_returns_1(monkeypatch, capsys):
    monkeypatch.setattr(resolver, "search_playlists", lambda q, count=5: [
        {"id": "PLtop", "name": "Empty", "owner": "X", "track_count": 0},
    ])
    monkeypatch.setattr(resolver, "playlist_tracks", lambda pid, limit=50: [])
    monkeypatch.setattr(cli.winamp, "play",
                        lambda tracks, port=0: pytest.fail("must not play"))
    rc = cli.main(["mix", "empty"])
    assert rc == 1
    assert "no tracks found" in capsys.readouterr().err
