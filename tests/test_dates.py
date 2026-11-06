"""Body dates, PolyU review-start dates, and the possibly-stale flag."""

from datetime import date

from sources.dates import extract_deadline, extract_review_start, refine_dates


TODAY = date(2026, 11, 6)


def test_appointment_start_and_funding_window_are_not_deadlines():
    start = "The appointee will support the project (Duration: 6 months to 1 year, starting in Fall 2025)."
    funding = "The post is funded under the 2025-28 triennium. Duties will commence on 1 September 2027."
    assert extract_deadline(start) is None
    assert extract_review_start(start) is None
    assert extract_deadline(funding) is None
    stale = refine_dates({"content": start, "close_date": None, "open_date": "2025-06-01"}, today=TODAY)
    assert stale["close_date"] is None
    assert stale["date_type"] == "unspecified"
    assert stale["possibly_stale"] is True
    current = refine_dates({"content": funding, "close_date": None}, today=TODAY)
    assert current["close_date"] is None
    assert current["possibly_stale"] is False


def test_body_closing_and_review_phrases():
    closing = refine_dates(
        {"content": "Closing date: 15 December 2026. Apply by 15 December 2026.", "close_date": None},
        today=TODAY,
    )
    assert closing["close_date"] == "2026-12-15"
    assert closing["date_type"] == "deadline"
    assert closing["possibly_stale"] is False

    review = refine_dates(
        {
            "content": "Review of applications will begin on 13 November 2026 and continue until the positions are filled.",
            "close_date": None,
        },
        today=TODAY,
    )
    assert review["close_date"] == "2026-11-13"
    assert review["date_type"] == "review_start"
    assert review["possibly_stale"] is False

    considered = refine_dates(
        {
            "content": "Applications will be considered from 1 March 2026 until the positions are filled.",
            "close_date": None,
        },
        today=TODAY,
    )
    assert considered["date_type"] == "review_start"
    assert considered["close_date"] == "2026-03-01"


def test_polyu_listing_year_wins_over_the_advertisement():
    post = refine_dates(
        {
            "content": "Consideration of applications will commence on 22 June 2025 until the positions are filled.",
            "close_date": "2026-06-22",
            "date_type": "review_start",
        },
        today=TODAY,
    )
    assert post["close_date"] == "2026-06-22"
    assert post["date_type"] == "review_start"
    assert post["date_note"] == "Listing date 2026-06-22 kept; advertisement text says 2025-06-22."
    assert post["possibly_stale"] is False


def test_listing_deadline_is_kept_when_the_body_year_disagrees():
    post = refine_dates(
        {
            "content": "The closing date is 22 June 2025.",
            "close_date": "2026-06-22",
        },
        today=TODAY,
    )
    assert post["close_date"] == "2026-06-22"
    assert post["date_type"] == "deadline"
    assert "2025-06-22" in post["date_note"]


def test_open_until_filled_without_a_past_term_is_not_stale():
    post = refine_dates(
        {"content": "Applications are accepted until the position is filled.", "close_date": None},
        today=TODAY,
    )
    assert post["date_type"] == "open_until_filled"
    assert post["close_date"] is None
    assert post["possibly_stale"] is False
