"""Country detection and national number-one chart lists from Wikipedia.

Era hits differ per country, so the radio localizes: the user's country is
detected from their IP and the country's national number-one singles from
the Winamp years are pulled from Wikipedia's per-country chart lists (free
API, CC-BY-SA data). Countries without a known list fall back to the global
hit parade — the fetch never guesses, it just bows out.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG_DIR = Path.home() / ".ytm-winamp"
GEO_CACHE_PATH = CONFIG_DIR / "country.json"
GEO_CACHE_TTL = 30 * 24 * 3600   # country rarely changes
CHART_CACHE_TTL = 7 * 24 * 3600
ERA_YEARS = range(1996, 2006)    # the Winamp decade
MAX_LOCAL_QUERIES = 80
USER_AGENT = "ytm-winamp (+https://github.com/mcftira/ytm-winamp)"

# Verified Wikipedia page patterns for national number-one lists.
# Values are (wiki lang, (page title templates,)); templates are tried in
# order until one yields hits (404s are skipped). Placeholders: {year},
# {decade} ("1990s") and {country}. Decade and all-time list pages work too:
# rows outside ERA_YEARS are filtered out while parsing.
COUNTRY_SOURCES = {
    "DE": ("en", ("List of number-one hits of {year} (Germany)",)),
    "AT": ("en", ("List of number-one hits of {year} (Austria)",)),
    "CH": ("en", ("List of number-one hits of {year} (Switzerland)",)),
    "IT": ("en", ("List of number-one hits of {year} (Italy)",)),
    "ES": ("en", ("List of number-one singles of {year} (Spain)",)),
    "NL": ("en", ("List of Dutch Top 40 number-one singles of {year}",)),
    "FR": ("en", ("List of number-one hits of {year} (France)",)),
    "IE": ("en", ("List of number-one singles of {year} (Ireland)",)),
    "BE": ("en", ("Ultratop 40 number-one hits of {year}",)),
    "DK": ("en", ("List of number-one hits of {year} (Denmark)",)),
    "FI": ("en", ("List of number-one singles of {year} (Finland)",)),
    "SE": ("en", ("List of number-one singles and albums in Sweden",)),
    "NO": ("en", ("List of number-one songs in Norway",)),
    "GB": ("en", ("List of UK singles chart number ones of the {decade}",)),
    "AU": ("en", ("List of top 25 singles for {year} in Australia",)),
    "NZ": ("en", ("List of number-one singles from the {decade} (New Zealand)",)),
    "CA": ("en", ("List of number-one singles of {year} (Canada)",)),
    "US": ("en", ("List of Billboard Hot 100 number ones of {year}",)),
    "JP": ("en", ("List of Oricon number-one singles of {year}",)),
}

COUNTRY_NAMES = {
    "DE": "Germany", "AT": "Austria", "CH": "Switzerland", "IT": "Italy",
    "ES": "Spain", "NL": "Netherlands", "FR": "France",
    "IE": "Ireland", "BE": "Belgium", "DK": "Denmark", "FI": "Finland",
    "SE": "Sweden", "NO": "Norway", "GB": "United Kingdom", "AU": "Australia",
    "NZ": "New Zealand", "CA": "Canada", "US": "United States", "JP": "Japan",
}

_SONG_HEADERS = re.compile(
    r"song|title|track|single|album|dal|szám|titel|canción|brano|titre"
    r"|utwór|lied", re.I)
_ARTIST_HEADERS = re.compile(
    r"artist|performer|interpret|előadó|artista|künstler|artiste|wykonawca", re.I)
_REF_RE = re.compile(r"\[\s*\d+\s*\]|\[(?:note|no)\.?\s*\d*\]", re.I)
_QUOTES_RE = re.compile(r"^[\"'„“”‚‘’]+|[\"'„“”‚‘’]+$")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_DECADE_RE = re.compile(r"\b((?:19|20)\d{2})s\b")


def _get(url: str, timeout: int = 15) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def detect_country() -> tuple[str | None, str | None]:
    """Return (country code, country name) for the user's IP, cached."""
    try:
        cached = json.loads(GEO_CACHE_PATH.read_text(encoding="utf-8"))
        if time.time() - cached.get("at", 0) < GEO_CACHE_TTL:
            return cached.get("cc"), cached.get("name")
    except (OSError, json.JSONDecodeError):
        pass
    raw = _get("http://ip-api.com/json/?fields=status,countryCode,country")
    if not raw:
        return None, None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, None
    if data.get("status") != "success":
        return None, None
    cc, name = data.get("countryCode"), data.get("country")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    GEO_CACHE_PATH.write_text(
        json.dumps({"cc": cc, "name": name, "at": time.time()}),
        encoding="utf-8")
    return cc, name


def _clean(text: str) -> str:
    text = _REF_RE.sub("", text)
    text = text.replace("†", "").replace("\u00a0", " ")
    text = _QUOTES_RE.sub("", text.strip())
    return " ".join(text.split())


def _header_cols(texts: list[str]) -> tuple[int, int] | None:
    """(song col, artist col) when the row texts look like a chart header."""
    song_col = next((i for i, h in enumerate(texts) if _SONG_HEADERS.search(h)), None)
    artist_col = next((i for i, h in enumerate(texts) if _ARTIST_HEADERS.search(h)), None)
    if song_col is None or artist_col is None or song_col == artist_col:
        return None
    return song_col, artist_col


def _section_year(table) -> int | None:
    """The single year a table's section heading names, if unambiguous.

    Pages that split charts into one table per year ("1996", "2009") carry
    the year in the heading, not in the date cells. Headings with a range
    ("1995–2008") or no year return None and row-level checks decide.
    """
    heading = table.find_previous(["h2", "h3", "h4"])
    if heading is None:
        return None
    years = {int(y) for y in _YEAR_RE.findall(heading.get_text(" "))}
    return years.pop() if len(years) == 1 else None


def _title_years(soup) -> set[int]:
    """Years the page title scopes to ("...of 1998", "the 1990s").

    Used to place rows that carry no year themselves: on a page dedicated to
    in-range years they belong to the chart; on a page spanning out-of-range
    years (decade/all-time lists) they cannot be placed and are dropped.
    """
    heading = soup.find("h1")
    text = heading.get_text(" ") if heading else ""
    years = {int(y) for y in _YEAR_RE.findall(text)}
    for decade in _DECADE_RE.findall(text):
        years.update(range(int(decade), int(decade) + 10))
    return years


def parse_chart_page(html: str, years: set[int] | None = None) -> list[tuple[str, str]]:
    """Extract (song, artist) pairs from a Wikipedia number-one list page.

    Handles the common wikitable layouts: header rows naming the song and
    artist columns are re-detected per row, so tables with a leading title
    row ("Physical singles") or several stacked sections work; cells left
    empty when the entry is unchanged from the week above are forward-filled.
    When ``years`` is given, decade and all-time list pages stay usable:
    tables under a single out-of-range year heading are skipped wholesale,
    rows mentioning only out-of-range 4-digit years are dropped, and rows
    without any year are kept only when the page title itself is scoped to
    in-range years (or names no year at all).
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    title_years = _title_years(soup) if years is not None else set()
    pairs: list[tuple[str, str]] = []
    for table in soup.select("table.wikitable"):
        section_year = _section_year(table) if years is not None else None
        if section_year is not None and section_year not in years:
            continue
        cols: tuple[int, int] | None = None
        last_song = last_artist = ""
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            texts = [c.get_text(" ", strip=True) for c in cells]
            new_cols = _header_cols(texts)
            if new_cols is not None:  # a (sub-)header row: new column layout
                cols = new_cols
                last_song = last_artist = ""
                continue
            if cols is None or len(cells) <= max(cols):
                continue
            if years is not None and section_year is None:
                row_years = {int(y) for y in _YEAR_RE.findall(" ".join(texts))}
                if row_years and row_years.isdisjoint(years):
                    continue
                if not row_years and title_years and not title_years <= years:
                    continue
            song = _clean(texts[cols[0]])
            artist = _clean(texts[cols[1]])
            if song:
                last_song = song
            if artist:
                last_artist = artist
            if last_song and last_artist:
                pairs.append((last_song, last_artist))
    seen: set[str] = set()
    unique = []
    for song, artist in pairs:
        key = f"{song}|{artist}".lower()
        if key not in seen:
            seen.add(key)
            unique.append((song, artist))
    return unique


def _chart_cache_path(cc: str) -> Path:
    return CONFIG_DIR / f"charts_{cc.lower()}.json"


def _patterns_for(cc: str, country_name: str | None) -> list[tuple[str, str]]:
    """(wiki lang, page title template) candidates for a country."""
    if cc in COUNTRY_SOURCES:
        lang, templates = COUNTRY_SOURCES[cc]
        if isinstance(templates, str):  # legacy single-template entries
            templates = (templates,)
        return [(lang, template) for template in templates]
    if country_name:
        return [
            ("en", "List of number-one hits of {year} ({country})"),
            ("en", "List of number-one singles of {year} ({country})"),
        ]
    return []


def parse_slagerlistak_page(html: str) -> list[tuple[str, str]]:
    """Extract (song, artist) pairs from a slagerlistak.hu year chart.

    Their yearly aggregated tables mark each entry up as
    ``<span class="eloado">Artist</span><br/>Title<br/><span>(Label)</span>``.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    pairs: list[tuple[str, str]] = []
    for td in soup.select("td[class^='lemez_sor']"):
        artist_el = td.find("span", class_="eloado")
        if not artist_el:
            continue
        artist = _clean(artist_el.get_text(" ", strip=True))
        for label in td.find_all("span", class_="kiado_sor"):
            label.decompose()
        parts = [p for p in (t.strip() for t in td.get_text("|").split("|")) if p]
        if len(parts) >= 2 and artist:
            pairs.append((_clean(parts[1]), artist))
    seen: set[str] = set()
    unique = []
    for song, artist in pairs:
        key = f"{song}|{artist}".lower()
        if song and key not in seen:
            seen.add(key)
            unique.append((song, artist))
    return unique


def _fetch_slagerlistak_hu(years) -> list[str]:
    """Hungarian Rádiós Top 40 year-end charts from slagerlistak.hu."""
    queries: list[str] = []
    for year in years:
        url = ("https://slagerlistak.hu/archivum/"
               f"eves-osszesitett-slagerlistak/radios/{year}")
        html = _get(url)
        if not html:
            continue
        for song, artist in parse_slagerlistak_page(html):
            queries.append(f"{artist} - {song}")
    return queries


# Bespoke fetchers for countries without a Wikipedia number-one list.
_BESPOKE_FETCHERS = {"HU": _fetch_slagerlistak_hu}


def fetch_chart_queries(cc: str, country_name: str | None = None,
                        years=ERA_YEARS) -> list[str]:
    """Return "Artist - Song" queries for a country's era number-one hits.

    Results are cached per country for a week. Returns an empty list when
    no chart list is known for the country or the fetch fails.
    """
    cc = cc.upper()
    try:
        cached = json.loads(_chart_cache_path(cc).read_text(encoding="utf-8"))
        if time.time() - cached.get("at", 0) < CHART_CACHE_TTL:
            return cached.get("queries", [])
    except (OSError, json.JSONDecodeError):
        pass
    queries: list[str] = []
    seen: set[str] = set()
    year_set = set(years)
    seen_titles: set[str] = set()
    for lang, template in _patterns_for(cc, country_name):
        for year in years:
            title = template.format(year=year, decade=f"{year // 10 * 10}s",
                                    country=country_name or "")
            if title in seen_titles:  # decade/all-time pages repeat per year
                continue
            seen_titles.add(title)
            url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title)}"
            html = _get(url)
            if html is None or "Wikipedia does not have an article" in html:
                continue
            for song, artist in parse_chart_page(html, years=year_set):
                query = f"{artist} - {song}"
                if query.lower() not in seen:
                    seen.add(query.lower())
                    queries.append(query)
        if queries:  # a working pattern: stop trying alternatives
            break
    if not queries and cc in _BESPOKE_FETCHERS:
        for query in _BESPOKE_FETCHERS[cc](years):
            if query.lower() not in seen:
                seen.add(query.lower())
                queries.append(query)
    if len(queries) > MAX_LOCAL_QUERIES:
        # take an even spread so every era year keeps some hits (the lists
        # are chronological; plain truncation would keep only the first years)
        step = len(queries) / MAX_LOCAL_QUERIES
        queries = [queries[int(i * step)] for i in range(MAX_LOCAL_QUERIES)]
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _chart_cache_path(cc).write_text(
        json.dumps({"at": time.time(), "queries": queries}, ensure_ascii=False),
        encoding="utf-8")
    return queries
