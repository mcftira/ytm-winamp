"""Offline unit tests for HTTP Range (seeking) support in the bridge.

Handler-level tests: a BridgeHandler is built without a socket, with a
BytesIO wfile and dict headers, so no network and no Winamp are involved.
"""
import io
from types import SimpleNamespace

import pytest

from ytm_winamp import server
from ytm_winamp.server import BridgeHandler, TrackCache, parse_range

VID = "eNvUS-6PTbs"
DATA = b"0123456789"  # 10 bytes of fake MP3


def _make_ready(cache: TrackCache, vid: str = VID) -> None:
    cache.mp3_path(vid).write_bytes(DATA)
    cache.done_path(vid).touch()


def _request(cache: TrackCache, headers: dict | None = None):
    """Run one GET /stream/<vid> through the handler; return (status, hdrs, body)."""
    h = BridgeHandler.__new__(BridgeHandler)  # skip socket setup in __init__
    h.wfile = io.BytesIO()
    h.rfile = io.BytesIO()
    h.headers = headers or {}
    h.client_address = ("127.0.0.1", 12345)
    h.path = f"/stream/{VID}.mp3"
    h.requestline = f"GET {h.path} HTTP/1.1"  # used by log_request
    h.request_version = "HTTP/1.1"            # checked by send_response_only
    h.command = "GET"
    h.server = SimpleNamespace(cache=cache)
    h.do_GET()
    head, _, body = h.wfile.getvalue().partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status = int(lines[0].split()[1])
    hdrs = {}
    for line in lines[1:]:
        key, _, value = line.partition(b": ")
        hdrs[key.decode().lower()] = value.decode()
    return status, hdrs, body


# --- parse_range: pure parsing -------------------------------------------

def test_parse_range_start_end():
    assert parse_range("bytes=100-199", 1000) == (100, 199)


def test_parse_range_open_end():
    assert parse_range("bytes=100-", 1000) == (100, 999)


def test_parse_range_suffix():
    assert parse_range("bytes=-100", 1000) == (900, 999)


def test_parse_range_suffix_larger_than_file():
    assert parse_range("bytes=-2000", 1000) == (0, 999)


def test_parse_range_end_clamped_to_file():
    assert parse_range("bytes=0-99999", 1000) == (0, 999)


def test_parse_range_single_byte():
    assert parse_range("bytes=0-0", 1000) == (0, 0)


@pytest.mark.parametrize("header", [
    "bytes=1000-",    # starts past the end of the file
    "bytes=99-10",    # start after end
    "bytes=-0",       # zero-length suffix
    "bytes=",         # empty spec
    "bytes=-",        # missing both ends
    "bytes=abc-def",  # not numbers
    "bytes=1-2-3",    # malformed spec
    "items=0-10",     # unsupported unit
    "bytes=0-10,20-30",  # multi-range would need multipart
    "gibberish",
])
def test_parse_range_unsatisfiable_or_invalid(header):
    assert parse_range(header, 1000) is None


def test_parse_range_empty_file():
    assert parse_range("bytes=0-0", 0) is None


# --- handler: normal 200 responses ----------------------------------------

def test_ready_200_advertises_accept_ranges(tmp_path):
    cache = TrackCache(tmp_path, start_worker=False)
    _make_ready(cache)
    status, hdrs, body = _request(cache)
    assert status == 200
    assert hdrs["accept-ranges"] == "bytes"
    assert hdrs["content-length"] == str(len(DATA))
    assert body == DATA


def test_ready_200_with_icy_also_advertises_accept_ranges(tmp_path):
    cache = TrackCache(tmp_path, start_worker=False)
    _make_ready(cache)
    status, hdrs, body = _request(cache, {"Icy-MetaData": "1"})
    assert status == 200
    assert hdrs["accept-ranges"] == "bytes"
    assert hdrs["icy-metaint"] == str(server.ICY_METAINT)
    assert "content-length" not in hdrs  # metadata blocks shift the total


# --- handler: 206 partial content -----------------------------------------

def test_range_206_serves_requested_slice(tmp_path):
    cache = TrackCache(tmp_path, start_worker=False)
    _make_ready(cache)
    status, hdrs, body = _request(cache, {"Range": "bytes=2-5"})
    assert status == 206
    assert hdrs["content-range"] == f"bytes 2-5/{len(DATA)}"
    assert hdrs["content-length"] == "4"
    assert hdrs["accept-ranges"] == "bytes"
    assert hdrs["content-type"] == "audio/mpeg"
    assert body == DATA[2:6]


def test_range_206_open_end_and_suffix(tmp_path):
    cache = TrackCache(tmp_path, start_worker=False)
    _make_ready(cache)
    status, hdrs, body = _request(cache, {"Range": "bytes=7-"})
    assert (status, hdrs["content-range"], body) == \
        (206, f"bytes 7-9/{len(DATA)}", DATA[7:])
    status, hdrs, body = _request(cache, {"Range": "bytes=-3"})
    assert (status, hdrs["content-range"], body) == \
        (206, f"bytes 7-9/{len(DATA)}", DATA[-3:])


def test_range_206_never_interleaves_icy(tmp_path):
    cache = TrackCache(tmp_path, start_worker=False)
    _make_ready(cache)
    status, hdrs, body = _request(
        cache, {"Range": "bytes=2-5", "Icy-MetaData": "1"})
    assert status == 206
    assert "icy-metaint" not in hdrs
    assert "icy-name" not in hdrs
    assert body == DATA[2:6]  # exactly the slice, no metadata blocks


# --- handler: 416 range not satisfiable ------------------------------------

def test_range_out_of_bounds_416(tmp_path):
    cache = TrackCache(tmp_path, start_worker=False)
    _make_ready(cache)
    status, hdrs, body = _request(cache, {"Range": "bytes=999999-"})
    assert status == 416
    assert hdrs["content-range"] == f"bytes */{len(DATA)}"
    assert hdrs["content-length"] == "0"
    assert body == b""


def test_range_malformed_416(tmp_path):
    cache = TrackCache(tmp_path, start_worker=False)
    _make_ready(cache)
    status, hdrs, _ = _request(cache, {"Range": "gibberish"})
    assert status == 416
    assert hdrs["content-range"] == f"bytes */{len(DATA)}"


# --- handler: range ignored while downloading ------------------------------

def test_range_ignored_while_downloading(tmp_path, monkeypatch):
    # mp3 exists but no .done marker: Range must be ignored, plain 200
    monkeypatch.setattr(server, "STALL_TIMEOUT", 0.3)  # don't wait 45s at EOF
    cache = TrackCache(tmp_path, start_worker=False)
    cache.mp3_path(VID).write_bytes(DATA)
    status, hdrs, body = _request(cache, {"Range": "bytes=2-5"})
    assert status == 200
    assert "content-range" not in hdrs
    assert "accept-ranges" not in hdrs
    assert "content-length" not in hdrs  # still growing: length unknown
    assert body == DATA
