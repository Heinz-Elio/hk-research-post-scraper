"""Active posts follow the live listing; a review date does not retire them."""

import json
from types import SimpleNamespace

import main
from embeddings_store import EMBED_INPUT_VERSION
from sources.base import finish_listing, make_post, note_counts, prepare_posts, same_listing


def _bind(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ACTIVE_FILE", tmp_path / "research_posts.json")
    monkeypatch.setattr(main, "OUTDATED_FILE", tmp_path / "outdated_posts.json")
    monkeypatch.setattr(main, "PUBLIC_FILE", tmp_path / "docs" / "research_posts.json")
    monkeypatch.setattr(main, "EMBED_FILE", tmp_path / "docs" / "embeddings.json")
    monkeypatch.setattr("sources.base._LISTING_HASH_PATH", tmp_path / "listing_hashes.json")


def _long(text: str) -> str:
    return text + (" Collect sources." * 8)


def test_fresh_list_drops_missing_ids_and_keeps_review_and_listed_deadlines(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    seed = {
        "PolyU_old": {
            "id": "PolyU_old",
            "title": "Research Assistant",
            "source": "PolyU",
            "url": "http://old",
            "close_date": "2020-01-01",
            "summary": "- Dept: Maths\n- Role focus: Old post.",
        },
        "PolyU_keep": {
            "id": "PolyU_keep",
            "title": "Research Assistant",
            "source": "PolyU",
            "url": "http://keep",
            "close_date": "2020-01-01",
            "date_type": "review_start",
            "summary": "- Dept: Maths\n- Role focus: Keep.",
        },
        "CityU_past": {
            "id": "CityU_past",
            "title": "Research Assistant",
            "source": "CityU",
            "url": "http://past",
            "close_date": "2020-01-01",
            "summary": "- Dept: CS\n- Role focus: Gone from the board.",
        },
        "CityU_live": {
            "id": "CityU_live",
            "title": "Research Assistant",
            "source": "CityU",
            "url": "http://live",
            "close_date": "2020-01-01",
            "summary": "- Dept: CS\n- Role focus: Still listed.",
        },
        "HKU_review": {
            "id": "HKU_review",
            "title": "Research Assistant",
            "source": "HKU",
            "url": "http://hku",
            "close_date": "2020-06-01",
            "date_type": "review_start",
            "summary": "- Dept: History\n- Role focus: Not scraped this run.",
        },
    }
    main.save_json(main.ACTIVE_FILE, seed)
    main.save_json(main.OUTDATED_FILE, {})

    def scrape_polyu():
        note_counts("PolyU", 1, 1)
        same_listing("PolyU", ["keep|Research Assistant"])
        posts = [
            make_post(
                source="PolyU",
                ref="keep",
                title="Research Assistant",
                url="http://keep",
                content=_long(
                    "Department: Department of Applied Mathematics\n"
                    "Duties: Assist the project on viscoelasticity.\n"
                    "Requirements: A doctoral degree in mathematics.\n"
                    "Consideration of applications will commence on 22 June 2025 until the positions are filled."
                ),
                close_date="2026-06-22",
                department="Department of Applied Mathematics",
                date_type="review_start",
            )
        ]
        prepare_posts(posts)
        finish_listing("PolyU", posts)
        return posts

    def scrape_cityu():
        note_counts("CityU", 1, 1)
        same_listing("CityU", ["live|Research Assistant"])
        posts = [
            make_post(
                source="CityU",
                ref="live",
                title="Research Assistant",
                url="http://live",
                content=_long("Duties: Build data tools. Requirements: A bachelor degree in computer science. Closing date: 1 January 2020."),
                close_date="2020-01-01",
                department="Department of Computer Science",
            )
        ]
        prepare_posts(posts)
        finish_listing("CityU", posts)
        return posts

    monkeypatch.setattr(main, "SCRAPERS", {"PolyU": scrape_polyu, "CityU": scrape_cityu})
    main.run(sources=["PolyU", "CityU"], generate_embeddings=False, force=True)

    active = main.load_json(main.ACTIVE_FILE)
    outdated = main.load_json(main.OUTDATED_FILE)
    assert "PolyU_keep" in active
    assert active["PolyU_keep"]["date_type"] == "review_start"
    assert active["PolyU_keep"]["close_date"] == "2026-06-22"
    assert "2025-06-22" in active["PolyU_keep"]["date_note"]
    assert "University:" not in active["PolyU_keep"]["summary"]
    assert "CityU_live" in active
    assert "PolyU_old" in outdated
    assert "CityU_past" in outdated
    assert "HKU_review" in active

    hashes = json.loads((tmp_path / "listing_hashes.json").read_text())
    assert "PolyU" in hashes and "CityU" in hashes


def test_force_flag_is_accepted():
    parser_args = main.parse_args.__wrapped__ if hasattr(main.parse_args, "__wrapped__") else None
    assert parser_args is None
    import sys

    old = sys.argv
    try:
        sys.argv = ["main.py", "--ignore-hashes", "--sources", "HKU"]
        args = main.parse_args()
        assert args.force is True
        assert args.sources == "HKU"
        sys.argv = ["main.py", "--force", "--dry-run"]
        args = main.parse_args()
        assert args.force is True and args.dry_run is True
    finally:
        sys.argv = old


def test_migration_strips_contacts_and_rebuilds_old_vectors(tmp_path, monkeypatch):
    _bind(tmp_path, monkeypatch)
    active = {
        "id": "CityU_1", "source": "CityU", "title": "Research Assistant",
        "url": "https://example.org/jobs/1", "date_type": "open_until_filled",
        "summary": "- Role focus: Catalogue records. Tel: 3917 1234\n- Contact: Dr. Doe",
        "contact_email": "contact@example.org", "embedding": [0.75, 0.25],
        "internal_flag": "not a listing field",
    }
    old = {**active, "id": "CityU_2", "summary": "- Requirements: Archive work. Write to contact@example.org."}
    main.ACTIVE_FILE.write_text(json.dumps([active]), encoding="utf-8")
    main.OUTDATED_FILE.write_text(json.dumps([old]), encoding="utf-8")
    main.EMBED_FILE.parent.mkdir()
    main.EMBED_FILE.write_text(json.dumps({
        "items": {active["id"]: {"scale": 1, "q": [1, 1]}},
    }), encoding="utf-8")
    encoded = []

    def encode(texts, **_kwargs):
        encoded.extend(texts)
        return SimpleNamespace(tolist=lambda: [[1.0, -1.0]])

    monkeypatch.setattr(main, "HAS_EMBED", True)
    monkeypatch.setattr(main, "EMBED_MODEL", SimpleNamespace(encode=encode))
    main.run(scrape=False)

    for path in (main.ACTIVE_FILE, main.OUTDATED_FILE, main.PUBLIC_FILE):
        saved = next(iter(main.load_json(path).values()))
        assert saved["url"] == active["url"]
        assert "contact_email" not in saved and "embedding" not in saved
        assert not any(token in saved["summary"] for token in ("3917", "Dr. Doe", "@example.org", "Contact:"))
    public = main.load_json(main.PUBLIC_FILE)[active["id"]]
    assert "internal_flag" not in public
    assert len(encoded) == 1 and "Catalogue records." in encoded[0]
    assert "3917" not in encoded[0] and "Dr. Doe" not in encoded[0]
    store = json.loads(main.EMBED_FILE.read_text(encoding="utf-8"))
    assert store["input_version"] == EMBED_INPUT_VERSION
    assert store["items"][active["id"]]["q"] == [127, -127]
