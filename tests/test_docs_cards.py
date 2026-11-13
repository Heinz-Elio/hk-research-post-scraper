"""The static card renderer shows the job id, the date kind, and a stale badge."""

import subprocess
from pathlib import Path


HTML = Path(__file__).resolve().parents[1].joinpath("docs", "index.html").read_text(encoding="utf-8")


def test_cards_show_ref_date_kind_and_stale_badge():
    assert "function dateFooter" in HTML
    assert "p.id" in HTML
    assert 'kind === "review_start"' in HTML
    assert "open until filled" in HTML
    assert "Open until filled" in HTML
    assert "Closing date not specified" in HTML
    assert "possibly_stale" in HTML
    assert "Possibly stale" in HTML
    assert "badge-stale" in HTML
    assert '"health": "Health"' in HTML
    assert 'id="filter-contract"' in HTML
    assert 'id="filter-place"' in HTML
    assert 'id="filter-deadline"' in HTML
    assert "contractMatches" in HTML
    assert "Closing within 30 days" in HTML
    assert 'for="filter-source"' in HTML
    assert 'for="filter-work"' in HTML
    assert 'for="filter-held"' in HTML
    assert 'for="filter-requires"' in HTML
    assert 'for="filter-contract"' in HTML
    assert 'for="filter-place"' in HTML
    assert 'for="filter-deadline"' in HTML
    assert 'for="sort-by"' in HTML
    assert 'for="search"' in HTML
    assert 'for="filter-shortlist"' in HTML
    assert 'for="filter-hide-applied"' in HTML
    assert 'value="unspecified">Unspecified' in HTML
    assert "Upcoming first" in HTML
    assert "function sortPosts" in HTML
    assert "function workMatches" in HTML
    assert "history.replaceState" in HTML
    assert "hkrps-shortlist" in HTML
    assert "hkrps-applied" in HTML
    assert "hkrps-seen-scraped-at" in HTML
    assert "Loading semantic search" in HTML
    assert "badge-new" in HTML
    assert "startSemantic()" in HTML
    # Embeddings and the model load on the first search, not during the initial fetch.
    assert "render();\n        initSemantic();" not in HTML


def test_browse_helpers_in_node():
    root = Path(__file__).resolve().parents[1]
    subprocess.check_call(["node", "tests/check_browse.mjs"], cwd=root)
