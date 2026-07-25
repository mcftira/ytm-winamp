"""Offline tests for the bridge RadioDirector (never-ending era radio)."""
from ytm_winamp import era
from ytm_winamp.resolver import Track
from ytm_winamp.server import RadioDirector, TrackCache


def _director(tmp_path):
    cache = TrackCache(tmp_path, start_worker=False)
    return RadioDirector(cache, port=8797, start_thread=False)


def test_should_extend_boundaries(tmp_path):
    d = _director(tmp_path)
    assert d._should_extend(length=10, pos=7)   # 3 left: extend
    assert d._should_extend(length=10, pos=9)   # 1 left: extend
    assert not d._should_extend(length=10, pos=6)  # 4 left: wait
    assert not d._should_extend(length=0, pos=0)   # no playlist: noop


def test_configure_resets_session(tmp_path):
    d = _director(tmp_path)
    d.used = {"old a", "old b"}
    d.configure({"country": "HU", "local": True}, ["Query A", "Query B"])
    assert d.recipe["country"] == "HU"
    assert d.used == {"query a", "query b"}  # fresh session, lowercased


def test_next_batch_excludes_used_and_accumulates(tmp_path, monkeypatch):
    d = _director(tmp_path)
    d.recipe = {"country": None, "local": True}
    d.used = {"already played"}
    captured = {}

    def fake_select(count, country, local, exclude, **kw):
        captured["exclude"] = set(exclude)
        return ["Brand New Song"], "note"

    monkeypatch.setattr(era, "select_queries", fake_select)
    monkeypatch.setattr(era, "resolve_queries",
                        lambda queries: [Track("abcdefghijk", "Song", "Artist", 200)])
    tracks = d._next_batch()
    assert captured["exclude"] == {"already played"}
    assert d.used == {"already played", "brand new song"}
    assert tracks[0].video_id == "abcdefghijk"


def test_maybe_extend_enqueues_batch(tmp_path, monkeypatch):
    d = _director(tmp_path)
    d.recipe = {"country": None, "local": True}
    monkeypatch.setattr(d, "_winamp_state", lambda: (1, 7, 10))
    batch = [Track("abcdefghijk", "One", "A", 100),
             Track("klmnopqrstu", "Two", "B", 100)]
    monkeypatch.setattr(d, "_next_batch", lambda: batch)
    enqueued = []
    monkeypatch.setattr(d, "_enqueue", enqueued.append)
    d._maybe_extend()
    assert enqueued == batch


def test_maybe_extend_noop_when_plenty_left(tmp_path, monkeypatch):
    d = _director(tmp_path)
    d.recipe = {"country": None, "local": True}
    monkeypatch.setattr(d, "_winamp_state", lambda: (1, 0, 10))
    monkeypatch.setattr(d, "_enqueue",
                        lambda t: (_ for _ in ()).throw(AssertionError("enqueue called")))
    d._maybe_extend()  # must not raise / enqueue
