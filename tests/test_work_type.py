"""Work type is taken only from an explicit phrase in the title or summary."""

from taxonomy import enrich_classification, extract_work_type


def test_extract_work_type_reads_explicit_phrases():
    assert extract_work_type("Research Assistant", "This is a full-time appointment.") == "Full-time"
    assert extract_work_type("Research Assistant", "Part-time, fractional basis.") == "Part-time"
    assert extract_work_type("Research Assistant", "Full time or part time.") == "Full-time/Part-time"
    assert extract_work_type("Research Assistant", "hourly-paid teaching support") == "Part-time"
    assert extract_work_type("研究助理", "職位為全職。") == "Full-time"
    assert extract_work_type("研究助理", "可全職或兼職。") == "Full-time/Part-time"
    assert extract_work_type("Research Assistant", "The appointee will conduct experiments.") is None


def test_enrich_sets_work_type_from_summary_and_does_not_guess():
    stated = {"id": "X", "title": "Research Assistant", "summary": "Appointment: full-time."}
    enrich_classification(stated)
    assert stated["work_type"] == "Full-time"

    silent = {"id": "Y", "title": "Postdoctoral Fellow", "summary": "The appointee will analyse data."}
    enrich_classification(silent)
    assert silent["work_type"] is None

    kept = {"id": "Z", "title": "Research Assistant", "summary": "No schedule given.", "work_type": "Part-time"}
    enrich_classification(kept)
    assert kept["work_type"] == "Part-time"
