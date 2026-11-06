"""Listing hashes are written only after a successful non-empty save."""

import json

from sources.base import (
    EMPTY_LISTING_HASH,
    commit_listing_hashes,
    configure_run,
    finish_listing,
    same_listing,
)


def _use(tmp_path, monkeypatch):
    path = tmp_path / "listing_hashes.json"
    monkeypatch.setattr("sources.base._LISTING_HASH_PATH", path)
    configure_run()
    return path


def test_finish_listing_does_not_write_until_commit(tmp_path, monkeypatch):
    path = _use(tmp_path, monkeypatch)
    assert same_listing("CityU", ["ref|title"]) is False
    finish_listing("CityU", [{"content": "x" * 100}])
    assert not path.exists()
    commit_listing_hashes()
    saved = json.loads(path.read_text())
    assert saved["CityU"] != EMPTY_LISTING_HASH


def test_empty_listing_and_empty_result_are_not_stored(tmp_path, monkeypatch):
    path = _use(tmp_path, monkeypatch)
    path.write_text(json.dumps({"HKU": EMPTY_LISTING_HASH}))
    configure_run()
    assert same_listing("HKU", []) is False
    assert same_listing("HKU", ["a real row"]) is False
    finish_listing("HKU", [])
    commit_listing_hashes()
    assert json.loads(path.read_text()) == {"HKU": EMPTY_LISTING_HASH}

    same_listing("EdUHK", ["only-row"])
    finish_listing("EdUHK", [{"content": "too short"}])
    commit_listing_hashes()
    assert "EdUHK" not in json.loads(path.read_text())


def test_zero_stored_posts_and_force_ignore_a_matching_hash(tmp_path, monkeypatch):
    path = _use(tmp_path, monkeypatch)
    rows = ["job|Research Assistant"]
    same_listing("HKMU", rows)
    finish_listing("HKMU", [{"content": "y" * 90}])
    commit_listing_hashes()
    fingerprint = json.loads(path.read_text())["HKMU"]

    configure_run(force=False, sources_with_no_posts=set())
    assert same_listing("HKMU", rows) is True

    configure_run(force=False, sources_with_no_posts={"HKMU"})
    assert same_listing("HKMU", rows) is False

    configure_run(force=True)
    assert same_listing("HKMU", rows) is False
    assert fingerprint
