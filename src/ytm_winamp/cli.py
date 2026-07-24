"""Command-line interface for ytm-winamp."""
from __future__ import annotations

import argparse
import sys

from . import __version__, resolver, winamp


def _cmd_play(args) -> int:
    query = " ".join(args.query)
    if resolver.is_url(query):
        tracks = resolver.resolve(query)
    else:
        # queue the top search hits so Winamp's next/previous buttons
        # actually have somewhere to go, like a YouTube Music radio queue
        tracks = resolver.search(query, count=args.count)
    if not tracks:
        print("no tracks found", file=sys.stderr)
        return 1
    winamp.play(tracks, port=args.port)
    if len(tracks) == 1:
        print(f"playing in Winamp: {tracks[0].display}")
    else:
        print(f"playing in Winamp: {tracks[0].display} (+{len(tracks) - 1} more in queue)")
    return 0


def _cmd_search(args) -> int:
    results = resolver.search(" ".join(args.query), count=args.count)
    for i, t in enumerate(results, 1):
        dur = f"{t.duration // 60}:{t.duration % 60:02d}" if t.duration else "?:??"
        print(f"{i:2d}. [{dur}] {t.display}\n     {t.watch_url}")
    if not results:
        return 1
    return 0


def _cmd_serve(args) -> int:
    from .server import run

    run(args.port)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ytm-winamp",
        description="Play YouTube Music tracks and playlists in classic Winamp.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("play", help="play a search query, video URL or playlist URL")
    p.add_argument("query", nargs="+", help="search words or a YouTube/YouTube Music URL")
    p.add_argument("-n", "--count", type=int, default=5,
                   help="search: queue this many top results (default 5)")
    p.add_argument("--port", type=int, default=winamp.DEFAULT_PORT)
    p.set_defaults(func=_cmd_play)

    s = sub.add_parser("search", help="list search results with their URLs")
    s.add_argument("query", nargs="+")
    s.add_argument("-n", "--count", type=int, default=5)
    s.set_defaults(func=_cmd_search)

    v = sub.add_parser("serve", help="run the bridge server in the foreground")
    v.add_argument("--port", type=int, default=winamp.DEFAULT_PORT)
    v.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (winamp.WinampError, resolver.DownloadError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
