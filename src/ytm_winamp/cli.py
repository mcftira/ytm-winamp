"""Command-line interface for ytm-winamp."""
from __future__ import annotations

import argparse
import random
import sys

from . import __version__, resolver, winamp


def _play_tracks(tracks, port: int) -> int:
    if not tracks:
        print("no tracks found", file=sys.stderr)
        return 1
    winamp.play(tracks, port=port)
    if len(tracks) == 1:
        print(f"playing in Winamp: {tracks[0].display}")
    else:
        print(f"playing in Winamp: {tracks[0].display} (+{len(tracks) - 1} more in queue)")
    return 0


def _cmd_play(args) -> int:
    query = " ".join(args.query)
    if resolver.is_url(query):
        tracks = resolver.resolve(query)
    else:
        # queue the top search hits so Winamp's next/previous buttons
        # actually have somewhere to go, like a YouTube Music radio queue
        tracks = resolver.search(query, count=args.count)
    return _play_tracks(tracks, args.port)


def _cmd_liked(args) -> int:
    tracks = resolver.liked_songs(auth=args.auth, limit=args.limit)
    if args.shuffle:
        random.shuffle(tracks)
    return _play_tracks(tracks, args.port)


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
    # tolerate legacy Windows consoles (cp1252) when printing track titles
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog="ytm-winamp",
        description="Play YouTube Music tracks and playlists in classic Winamp.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("play", help="play a search query, video URL or playlist URL")
    p.add_argument("query", nargs="+", help="search words or a YouTube/YouTube Music URL")
    p.add_argument("-n", "--count", type=int, default=5,
                   help="search: queue this many top results (default 5)")
    p.add_argument("--port", type=int, default=winamp.DEFAULT_PORT)
    p.set_defaults(func=_cmd_play)

    lk = sub.add_parser("liked", help="play your YouTube Music liked songs (default)")
    lk.add_argument("--auth", help="path to the ytmusicapi auth file")
    lk.add_argument("--limit", type=int, default=250,
                    help="how many liked songs to queue (default 250)")
    lk.add_argument("--shuffle", action="store_true", help="shuffle before queueing")
    lk.add_argument("--port", type=int, default=winamp.DEFAULT_PORT)
    lk.set_defaults(func=_cmd_liked)

    s = sub.add_parser("search", help="list search results with their URLs")
    s.add_argument("query", nargs="+")
    s.add_argument("-n", "--count", type=int, default=5)
    s.set_defaults(func=_cmd_search)

    v = sub.add_parser("serve", help="run the bridge server in the foreground")
    v.add_argument("--port", type=int, default=winamp.DEFAULT_PORT)
    v.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    if args.command is None:
        # bare `ytm-winamp`: the default queue is the user's liked songs
        args = parser.parse_args(["liked"])
    try:
        return args.func(args)
    except (winamp.WinampError, resolver.DownloadError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
