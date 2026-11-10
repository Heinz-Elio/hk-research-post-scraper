"""The static card renderer shows the job id, the date kind, and a stale badge."""

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
