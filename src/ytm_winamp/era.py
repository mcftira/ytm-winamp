"""Curated Winamp-era tracks (roughly 1995-2005), resolved via YouTube search.

No account or API key needed: each entry is a plain search string resolved
through yt-dlp's ``ytsearch``. Resolutions are cached on disk for a week, so
only the first run pays the search cost.

The queue mixes a global hit parade (the songs that topped charts
everywhere) with number-one hits from the user's own country, fetched from
Wikipedia's national chart lists (see charts.py).
"""
from __future__ import annotations

import json
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import charts
from .resolver import Track, search

ERA_CACHE_PATH = Path.home() / ".ytm-winamp" / "era_cache.json"
CACHE_TTL = 7 * 24 * 3600  # seconds; video availability drifts over time

# The stuff every late-90s/2000s Winamp playlist was made of, wherever you
# lived: the worldwide chart-toppers that go into every country's queue.
TRACKS = [
    "Darude - Sandstorm",
    "Eiffel 65 - Blue Da Ba Dee",
    "Zombie Nation - Kernkraft 400",
    "Alice Deejay - Better Off Alone",
    "ATB - 9PM Till I Come",
    "Gigi D'Agostino - L'amour Toujours",
    "Vengaboys - Boom Boom Boom Boom",
    "Aqua - Barbie Girl",
    "O-Zone - Dragostea Din Tei",
    "Cascada - Everytime We Touch",
    "Haddaway - What Is Love",
    "Snap! - Rhythm Is a Dancer",
    "La Bouche - Be My Lover",
    "Corona - The Rhythm of the Night",
    "Real McCoy - Another Night",
    "Mr. President - Coco Jamboo",
    "Rednex - Cotton Eye Joe",
    "Whigfield - Saturday Night",
    "Technotronic - Pump Up the Jam",
    "Robin S - Show Me Love",
    "Crystal Waters - Gypsy Woman",
    "Black Box - Ride on Time",
    "Modjo - Lady Hear Me Tonight",
    "Daft Punk - One More Time",
    "Benny Benassi - Satisfaction",
    "Faithless - Insomnia",
    "Robert Miles - Children",
    "Sash! - Ecuador",
    "Fragma - Toca's Miracle",
    "DJ Sammy - Heaven",
    "Ian Van Dahl - Castles in the Sky",
    "Lasgo - Something",
    "Milk Inc - Walk on Water",
    "Scooter - Ramp! The Logical Song",
    "Groove Coverage - God Is a Girl",
    "t.A.T.u. - All The Things She Said",
    "Modern Talking - Brother Louie 98",
    "Bad Boys Blue - You're a Woman",
    "Ace of Base - All That She Wants",
    "Dr. Alban - It's My Life",
    "2 Unlimited - No Limit",
    "Captain Jack - Captain Jack",
    "DJ Bobo - Freedom",
    "Culture Beat - Mr. Vain",
]

LOCAL_SHARE = 0.4  # fraction of the queue filled with the user's local hits


def select_queries(count: int, shuffle: bool = True,
                   country: str | None = None, local: bool = True,
                   rng: random.Random | None = None) -> tuple[list[str], str]:
    """Pick era search queries: a global core plus local number-one hits.

    Returns (queries, note) where note describes the localization outcome
    for the user, e.g. which country's charts were mixed in.
    """
    rand = rng or random
    local_queries: list[str] = []
    note = "global hits only"
    if local:
        try:
            if country:
                cc, name = country.upper(), charts.COUNTRY_NAMES.get(country.upper())
                if len(country) > 2:  # a full country name was passed
                    name = country
            else:
                cc, name = charts.detect_country()
            if cc:
                local_queries = charts.fetch_chart_queries(cc, name)
                if local_queries:
                    note = f"mixed with {name or cc} number-one hits"
                else:
                    note = f"no local chart list for {name or cc} yet; global hits only"
            else:
                note = "country detection failed; global hits only"
        except Exception as exc:  # localization must never sink the radio
            note = f"local charts unavailable ({exc}); global hits only"
    n_local = min(len(local_queries), round(count * LOCAL_SHARE))
    global_pool = list(dict.fromkeys(TRACKS))  # dedup, keep order
    # never queue the same song twice: local hits that are already in the
    # global canon belong to the canon, not to the local share
    global_keys = {t.lower() for t in global_pool}
    local_queries = [q for q in local_queries if q.lower() not in global_keys]
    n_local = min(n_local, len(local_queries))
    global_picks = rand.sample(global_pool, min(count - n_local, len(global_pool)))
    local_picks = rand.sample(local_queries, n_local) if n_local else []
    queries = global_picks + local_picks
    if shuffle:
        rand.shuffle(queries)
    return queries, note


def _load_cache(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    cutoff = time.time() - CACHE_TTL
    return {q: e for q, e in data.items() if e.get("resolved_at", 0) > cutoff}


def _save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def _resolve(query: str):
    try:
        results = search(query, count=1)
        if results:
            return query, results[0]
    except Exception:  # a failed search must not sink the whole queue
        pass
    return query, None


def era_tracks(count: int = 25, shuffle: bool = True,
               country: str | None = None, local: bool = True,
               cache_path: Path = ERA_CACHE_PATH) -> tuple[list[Track], str]:
    """Resolve ``count`` era tracks; the first run pays one search per track."""
    queries, note = select_queries(count, shuffle=shuffle,
                                   country=country, local=local)
    cache = _load_cache(cache_path)
    missing = [q for q in queries if q not in cache]
    if missing:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for query, track in pool.map(_resolve, missing):
                if track:
                    cache[query] = {
                        "video_id": track.video_id,
                        "title": track.title,
                        "uploader": track.uploader,
                        "duration": track.duration,
                        "resolved_at": time.time(),
                    }
        _save_cache(cache_path, cache)
    tracks = []
    for query in queries:
        entry = cache.get(query)
        if entry:
            tracks.append(Track(
                video_id=entry["video_id"],
                title=entry["title"],
                uploader=entry.get("uploader", ""),
                duration=int(entry.get("duration") or 0),
            ))
    return tracks, note
