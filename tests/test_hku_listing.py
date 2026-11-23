"""HKU lists every job twice and paginates. Read one table and follow pages."""

import json
from unittest.mock import patch

from bs4 import BeautifulSoup

import main
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


def test_hku_fetch_history_and_incomplete_listing_preserve_posts(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(main, "ACTIVE_FILE", tmp_path / "research_posts.json")
    monkeypatch.setattr(main, "OUTDATED_FILE", tmp_path / "outdated_posts.json")
    monkeypatch.setattr(main, "PUBLIC_FILE", tmp_path / "docs" / "research_posts.json")
    monkeypatch.setattr(main, "EMBED_FILE", tmp_path / "docs" / "embeddings.json")
    hashes = tmp_path / "listing_hashes.json"
    monkeypatch.setattr("sources.base._LISTING_HASH_PATH", hashes)
    pages = {1: PAGE_1.replace("2026-", "2099-"), 2: PAGE_2.replace("2026-", "2099-")}
    details = []

    def fake_fetch(url, **kwargs):
        if "/listing/" in url:
            page = 1 if "page=1" in url else 2
            return BeautifulSoup(pages[page], "lxml") if page in pages else None
        details.append(url)
        if "537776" in url:
            return None
        description = "Support sociology research and review relevant publications. " * 4
        return BeautifulSoup(f'<div id="job-content">{description}</div>', "lxml")

    with patch("sources.hku.fetch", side_effect=fake_fetch), patch("sources.hku.time.sleep"):
        main.run(sources=["HKU"], generate_embeddings=False)
        old_hash = hashes.read_text(encoding="utf-8")
        main.run(sources=["HKU"], generate_embeddings=False)
        del pages[2]
        main.run(sources=["HKU"], generate_embeddings=False)
        del pages[1]
        main.run(sources=["HKU"], generate_embeddings=False)

    records = [
        json.loads(line)
        for line in (tmp_path / "fetch_status.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [record["state"] for record in records] == ["complete", "unchanged", "partial", "failed"]
    assert all(record["source"] == "HKU" and record["run_started_at"] for record in records)
    assert records[0]["detail_attempts"] == 2
    assert records[0]["detail_missing"] == 1
    assert records[1]["detail_attempts"] == 0
    assert records[2]["pages_read"] == 1
    assert records[2]["reason"] == "page 2: listing unavailable"
    assert len(details) == 2
    assert "HKU_537776" in main.load_json(main.PUBLIC_FILE)
    assert "HKU_537776" not in main.load_json(main.OUTDATED_FILE)
    assert hashes.read_text(encoding="utf-8") == old_hash
    assert "HKU        partial" in capsys.readouterr().out
