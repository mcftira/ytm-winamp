"""Offline tests for the first-launch playlist handoff retry."""
import ytm_winamp.winamp as w
from ytm_winamp.resolver import Track


def _common_mocks(monkeypatch, tmp_path):
    monkeypatch.setattr(w, "ensure_server", lambda port: None)
    monkeypatch.setattr(w, "prefetch", lambda tracks, port, radio=None: None)
    monkeypatch.setattr(w, "find_winamp", lambda: tmp_path / "winamp.exe")
    monkeypatch.setattr(w, "write_playlist", lambda tracks, port: tmp_path / "pl.m3u8")
    launches = []
    monkeypatch.setattr(w.subprocess, "Popen", lambda argv, **kw: launches.append(argv))
    monkeypatch.setattr(w.time, "sleep", lambda s: None)
    return launches


def test_no_wait_when_winamp_already_running(monkeypatch, tmp_path):
    launches = _common_mocks(monkeypatch, tmp_path)
    monkeypatch.setattr(w, "_find_winamp_window", lambda: 12345)
    monkeypatch.setattr(w.time, "time", lambda: 0.0)  # would expire a wait instantly
    w.play([Track("abcdefghijk", "Song")])
    assert len(launches) == 1


def test_first_launch_playlist_loads_without_retry(monkeypatch, tmp_path):
    launches = _common_mocks(monkeypatch, tmp_path)
    state = {"calls": 0}

    def fake_find():
        state["calls"] += 1
        return 0 if state["calls"] == 1 else 12345  # not running, then running

    monkeypatch.setattr(w, "_find_winamp_window", fake_find)
    monkeypatch.setattr(w, "_playlist_length", lambda hwnd: 3)
    monkeypatch.setattr(w.time, "time", lambda: 0.0)
    w.play([Track("abcdefghijk", "A"), Track("bcdefghijkl", "B"),
            Track("cdefghijklm", "C")])
    assert len(launches) == 1


def test_first_launch_retries_when_handoff_lost(monkeypatch, tmp_path):
    launches = _common_mocks(monkeypatch, tmp_path)
    state = {"calls": 0}

    def fake_find():
        state["calls"] += 1
        return 0 if state["calls"] == 1 else 12345

    monkeypatch.setattr(w, "_find_winamp_window", fake_find)
    monkeypatch.setattr(w, "_playlist_length", lambda hwnd: 1)  # stuck on demo
    now = {"t": 0.0}

    def fake_time():
        now["t"] += 31.0  # burn the grace period immediately
        return now["t"]

    monkeypatch.setattr(w.time, "time", fake_time)
    w.play([Track("abcdefghijk", "A"), Track("bcdefghijkl", "B"),
            Track("cdefghijklm", "C")])
    assert len(launches) == 2
    assert launches[0] == launches[1]
