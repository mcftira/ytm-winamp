"""Offline unit tests for the charts module's generic wikitable parsing
and the multi-template country source map (no network, no Winamp).

Live verification of the actual Wikipedia pages is done manually; here we
pin the parser behavior with fixtures mirroring the real page layouts.
"""
import json

import pytest

from ytm_winamp import charts

ERA = set(charts.ERA_YEARS)


def _page(body: str, h1: str = "") -> str:
    heading = f"<h1>{h1}</h1>" if h1 else ""
    return f"<html><body>{heading}{body}</body></html>"


# --- parser layout fixtures ------------------------------------------------

# fi.wikipedia-style per-year page: a leading section-title row, then the
# real header; the singles column is (mis)labeled "Album".
FI_HTML = _page(
    """
    <table class="wikitable">
    <tr><th colspan="4">Physical singles</th></tr>
    <tr><th>Week</th><th>Album</th><th>Artist(s)</th><th>Reference(s)</th></tr>
    <tr><th>Week 1</th><td>"Pop-musiikkia"</td><td>Neljä baritonia</td><td>[1]</td></tr>
    <tr><th>Week 2</th><td>[2]</td><td>[3]</td><td>[4]</td></tr>
    <tr><th>Week 3</th><td>"Frozen"</td><td>Madonna</td><td>[5]</td></tr>
    </table>
    """, h1="List of number-one singles of 1998 (Finland)")


def test_parse_section_title_row_and_album_column():
    pairs = charts.parse_chart_page(FI_HTML, years={1998})
    assert pairs == [("Pop-musiikkia", "Neljä baritonia"), ("Frozen", "Madonna")]


def test_parse_repeated_header_rows_switch_columns():
    # a second header row mid-table (year-end table after a weekly table)
    html = _page(
        """
        <table class="wikitable">
        <tr><th>Date</th><th>Title</th><th>Artist</th></tr>
        <tr><td>January 6</td><td>"Believe"</td><td>Cher</td></tr>
        <tr><th>Pos.</th><th>Artist</th><th>Title</th></tr>
        <tr><td>1</td><td>Madonna</td><td>"Frozen"</td></tr>
        </table>
        """)
    pairs = charts.parse_chart_page(html)
    assert pairs == [("Believe", "Cher"), ("Frozen", "Madonna")]


def test_parse_years_filter_drops_out_of_range_rows():
    # GB-style decade page: every row carries a full date.
    html = _page(
        """
        <table class="wikitable">
        <tr><th>No.</th><th>Artist</th><th>Single</th><th>Week ending date</th></tr>
        <tr><td>1</td><td>Band Aid II</td><td>"Do They Know It's Christmas?"</td>
            <td>23 December 1989</td></tr>
        <tr><td>2</td><td>George Michael</td><td>"Jesus to a Child"</td>
            <td>27 January 1996</td></tr>
        </table>
        """, h1="List of UK singles chart number ones of the 1990s")
    assert charts.parse_chart_page(html) == [
        ("Do They Know It's Christmas?", "Band Aid II"),
        ("Jesus to a Child", "George Michael")]
    assert charts.parse_chart_page(html, years={1996}) == [
        ("Jesus to a Child", "George Michael")]


def test_parse_years_filter_skips_out_of_range_section_tables():
    # NZ-style decade page: one table per year under a year heading, and the
    # date cells carry no year of their own.
    html = _page(
        """
        <h2>1994</h2>
        <table class="wikitable">
        <tr><th>Date</th><th>Artist</th><th>Single</th></tr>
        <tr><td>7 January</td><td>Ace of Base</td><td>"The Sign"</td></tr>
        </table>
        <h2>1996</h2>
        <table class="wikitable">
        <tr><th>Date</th><th>Artist</th><th>Single</th></tr>
        <tr><td>6 January</td><td>Coolio</td><td>"Gangsta's Paradise"</td></tr>
        </table>
        """, h1="List of number-one singles from the 1990s (Nowhere)")
    assert charts.parse_chart_page(html, years={1996}) == [
        ("Gangsta's Paradise", "Coolio")]
    assert len(charts.parse_chart_page(html)) == 2


def test_parse_years_filter_uses_title_scope_for_yearless_rows():
    # summary table without any year in heading or rows: on a decade page
    # these rows cannot be placed and are dropped.
    html = _page(
        """
        <h2>2001</h2>
        <table class="wikitable">
        <tr><th>Date</th><th>Artist</th><th>Single</th></tr>
        <tr><td>5 January</td><td>Shaggy</td><td>"It Wasn't Me"</td></tr>
        </table>
        <h2>Most weeks at number one</h2>
        <table class="wikitable">
        <tr><th>Title</th><th>Artist</th><th>Weeks at number one</th></tr>
        <tr><td>"Poker Face"</td><td>Lady Gaga</td><td>5</td></tr>
        </table>
        """, h1="List of number-one singles from the 2000s (Nowhere)")
    assert charts.parse_chart_page(html, years=ERA) == [
        ("It Wasn't Me", "Shaggy")]


def test_parse_years_filter_keeps_yearless_rows_on_single_year_page():
    html = _page(
        """
        <table class="wikitable">
        <tr><th>Date</th><th>Title</th><th>Artist</th></tr>
        <tr><td>January 6</td><td>"Seul"</td><td>Garou</td></tr>
        </table>
        """, h1="Ultratop 40 number-one hits of 2001")
    assert charts.parse_chart_page(html, years=ERA) == [("Seul", "Garou")]


def test_parse_years_filter_range_heading_falls_back_to_rows():
    # NO/SE-style all-time page: a range heading, years only in the rows.
    html = _page(
        """
        <h2>1995–2008</h2>
        <table class="wikitable">
        <tr><th>Artist</th><th>Single</th><th>Reached number one</th></tr>
        <tr><td>Rednex</td><td>"Cotton Eye Joe"</td><td>10 October 1994</td></tr>
        <tr><td>Madonna</td><td>"Hung Up"</td><td>12 November 2005</td></tr>
        </table>
        """, h1="List of number-one songs in Nowhere")
    assert charts.parse_chart_page(html, years=ERA) == [("Hung Up", "Madonna")]


def test_clean_strips_no_style_footnotes():
    assert charts._clean('Re-Rewind " [No 2]') == "Re-Rewind"
    assert charts._clean("Believe [note 3]") == "Believe"


# --- COUNTRY_SOURCES / _patterns_for ----------------------------------------

def test_country_sources_all_normalize():
    for cc in charts.COUNTRY_SOURCES:
        patterns = charts._patterns_for(cc, charts.COUNTRY_NAMES.get(cc))
        assert patterns, cc
        for lang, template in patterns:
            assert isinstance(lang, str) and lang
            # renders with every supported placeholder, no stray fields
            assert template.format(year=2000, decade="2000s", country="X")


def test_patterns_for_multiple_templates(monkeypatch):
    monkeypatch.setitem(charts.COUNTRY_SOURCES, "XX",
                        ("en", ("First {year}", "Second {year}")))
    assert charts._patterns_for("XX", "Nowhere") == [
        ("en", "First {year}"), ("en", "Second {year}")]


def test_patterns_for_legacy_string_shape(monkeypatch):
    monkeypatch.setitem(charts.COUNTRY_SOURCES, "XY", ("en", "Only {year}"))
    assert charts._patterns_for("XY", "Nowhere") == [("en", "Only {year}")]


def test_patterns_for_fallback_and_unknown():
    patterns = charts._patterns_for("ZZ", "Nowhere")
    assert [t for _, t in patterns] == [
        "List of number-one hits of {year} ({country})",
        "List of number-one singles of {year} ({country})",
    ]
    assert charts._patterns_for("ZZ", None) == []


# --- fetch_chart_queries (offline, _get monkeypatched) ----------------------

CHART_PAGE = _page(
    """
    <table class="wikitable">
    <tr><th>Issue date</th><th>Song</th><th>Artist</th></tr>
    <tr><td>5 January</td><td>"Believe"</td><td>Cher</td></tr>
    <tr><td>12 January</td><td>"Frozen"</td><td>Madonna</td></tr>
    </table>
    """)


@pytest.fixture
def fake_wiki(monkeypatch, tmp_path):
    """Route charts._get to a URL->html dict and isolate the cache dir."""
    monkeypatch.setattr(charts, "CONFIG_DIR", tmp_path)
    pages: dict[str, str | None] = {}
    calls: list[str] = []

    def fake_get(url, timeout=15):
        calls.append(url)
        for key, html in pages.items():
            if key in url:
                return html
        return None

    monkeypatch.setattr(charts, "_get", fake_get)
    return pages, calls


def test_fetch_tries_alternative_templates(fake_wiki, monkeypatch):
    pages, calls = fake_wiki
    monkeypatch.setitem(charts.COUNTRY_SOURCES, "XX",
                        ("en", ("Nope {year}", "Yes {year}")))
    pages["Yes"] = CHART_PAGE
    queries = charts.fetch_chart_queries("XX", "Nowhere", years=(1998, 1999))
    assert queries == ["Cher - Believe", "Madonna - Frozen"]
    assert any("Nope" in url for url in calls)  # dead pattern tried first
    assert sum("Yes" in url for url in calls) == 2  # one page per year


def test_fetch_decade_template_fetched_once_per_decade(fake_wiki, monkeypatch):
    pages, calls = fake_wiki
    monkeypatch.setitem(charts.COUNTRY_SOURCES, "XY",
                        ("en", ("Number ones of the {decade}",)))
    pages["1990s"] = CHART_PAGE
    pages["2000s"] = CHART_PAGE
    queries = charts.fetch_chart_queries("XY", "Nowhere",
                                         years=(1996, 1997, 2000, 2001))
    assert queries == ["Cher - Believe", "Madonna - Frozen"]
    assert len(calls) == 2
    assert any("1990s" in url for url in calls)
    assert any("2000s" in url for url in calls)
    assert not any("1990ss" in url or "2000ss" in url for url in calls)


def test_fetch_caches_results_to_disk(fake_wiki, monkeypatch, tmp_path):
    pages, calls = fake_wiki
    monkeypatch.setitem(charts.COUNTRY_SOURCES, "XZ", ("en", ("Yes {year}",)))
    pages["Yes"] = CHART_PAGE
    first = charts.fetch_chart_queries("XZ", "Nowhere", years=(1998,))
    n_calls = len(calls)
    second = charts.fetch_chart_queries("XZ", "Nowhere", years=(1998,))
    assert first == second
    assert len(calls) == n_calls  # no refetch
    cached = json.loads((tmp_path / "charts_xz.json").read_text(encoding="utf-8"))
    assert cached["queries"] == first


def test_fetch_skips_pages_without_article(fake_wiki, monkeypatch):
    pages, calls = fake_wiki
    monkeypatch.setitem(charts.COUNTRY_SOURCES, "ZQ", ("en", ("Gone {year}",)))
    pages["Gone"] = "<html><body>Wikipedia does not have an article with this exact name.</body></html>"
    assert charts.fetch_chart_queries("ZQ", "Nowhere", years=(1998,)) == []


def test_fetch_falls_back_to_bespoke_fetcher(fake_wiki):
    pages, calls = fake_wiki
    pages["slagerlistak.hu"] = _page(
        """
        <table><tr>
        <td class="lemez_sor2"><span class="eloado">Dido</span><br />White Flag<br />
        <span class="kiado_sor">(BMG)</span></td>
        </tr></table>
        """)
    queries = charts.fetch_chart_queries("HU", "Hungary", years=(2003,))
    assert queries == ["Dido - White Flag"]
    assert any("slagerlistak.hu" in url for url in calls)


def test_fetch_spreads_queries_across_years(fake_wiki, monkeypatch):
    pages, calls = fake_wiki
    monkeypatch.setitem(charts.COUNTRY_SOURCES, "XS", ("en", ("Hits {year}",)))
    per_year = 12
    years = tuple(range(1996, 2006))

    def year_html(year):
        rows = "".join(
            f'<tr><td>Week {i}</td><td>"Hit {year} #{i}"</td>'
            f"<td>Artist {year}</td></tr>"
            for i in range(per_year))
        return _page(
            '<table class="wikitable">'
            "<tr><th>Week</th><th>Song</th><th>Artist</th></tr>"
            f"{rows}</table>")

    for year in years:
        pages[f"Hits%20{year}"] = year_html(year)
    queries = charts.fetch_chart_queries("XS", "Nowhere", years=years)
    assert len(queries) == charts.MAX_LOCAL_QUERIES
    assert len(queries) < per_year * len(years)  # the cap kicked in
    assert "1996" in queries[0] and "2005" in queries[-1]  # full era spread
    assert len(set(queries)) == len(queries)  # still unique
