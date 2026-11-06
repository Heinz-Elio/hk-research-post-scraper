"""HKU lists every job twice and paginates. Read one table and follow pages."""

from unittest.mock import patch

from bs4 import BeautifulSoup

from sources.hku import scrape


def _row(ref, title, dept, when):
    return f"""
    <tr>
      <td><span class="job-externalJobNo">{ref}</span></td>
      <td><a class="job-link" href="/en/job/{ref}/slug">{title}</a></td>
      <td>{dept}</td>
      <td><time datetime="{when}">{when}</time></td>
    </tr>
    """


def _page(rows, more=""):
    body = "\n".join(rows)
    return f"""
    <html><body>
      <table><tbody id="search-results-content">{body}</tbody></table>
      {more}
      <table><tbody id="recent-jobs-content">{body}</tbody></table>
      {more}
    </body></html>
    """


PAGE_1 = _page(
    [
        _row("537730", "Clerk II (holding the functional title of Executive Assistant)", "Faculty of Arts", "2026-11-30"),
        _row("537812", "Post-doctoral Fellow in the Department of Sociology", "Department of Sociology", "2026-12-15"),
    ],
    more='<a class="more-link" data-page="2" href="/en/listing/?page=2">More Jobs</a>',
)
PAGE_2 = _page(
    [
        _row("537812", "Post-doctoral Fellow in the Department of Sociology", "Department of Sociology", "2026-12-15"),
        _row("537776", "Senior Research Assistant in Dermatology", "School of Clinical Medicine", "2026-12-22"),
    ]
)


def test_hku_dedupes_the_two_tables_and_follows_pages():
    def fake_fetch(url, timeout=25, retry=3, wait_for=None):
        if "listing" in url:
            assert wait_for == "tbody#search-results-content"
        html = PAGE_1 if "page=1" in url else PAGE_2
        return BeautifulSoup(html, "lxml")

    with patch("sources.hku.fetch", side_effect=fake_fetch), \
         patch("sources.hku.same_listing", return_value=False), \
         patch("sources.hku.finish_listing"), \
         patch("sources.hku.time.sleep"):
        posts = scrape()
    ids = [post["id"] for post in posts]
    assert ids == ["HKU_537812", "HKU_537776"]
    assert all(post["date_type"] == "deadline" for post in posts)


def test_hku_missing_table_does_not_store_a_hash(tmp_path, monkeypatch):
    monkeypatch.setattr("sources.base._LISTING_HASH_PATH", tmp_path / "listing_hashes.json")
    empty = BeautifulSoup("<html><body><p>Sign in</p></body></html>", "lxml")
    with patch("sources.hku.fetch", return_value=empty), \
         patch("sources.hku.finish_listing") as finish, \
         patch("sources.hku.time.sleep"):
        assert scrape() == []
    finish.assert_not_called()
    assert not (tmp_path / "listing_hashes.json").exists()
