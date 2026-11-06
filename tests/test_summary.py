"""Concise extractive summaries, and rejection of a bad model rewrite."""

from summary import fact_summary, summarize, summary_needs_repair, validate_llm_summary


POLYU = """
Department: Department of Computing
Project Title: Crypto-based secure federated computation for large-scale data collaboration
Duties: Assist the project leader in conducting literature reviews, organizing research materials, and preparing reports, performing any other duties as assigned.
Requirements: An honours degree or above in Computer Science or Data Science, with experience in Python, knowledge of cryptography, and a command of written English. The University is an equal opportunity employer. Applicants not invited for interview will not be notified.
Appointment: 12 months, renewable
Salary: HK$20,000 per month
Contact: Ms Ada Chan, tel 2766 1234, yijia.chang@polyu.edu.hk
"""

HKU_DOUBLED = (
    "Research Assistant I/II in the Division of Epidemiology and Biostatistics "
    "Research Assistant I/II in the Division of Epidemiology and Biostatistics "
    "of the School of Public Health (Ref.: 537808). Applicants should possess a "
    "Bachelor's degree in public health and experience in biostatistics."
)


def _lines(summary: str):
    return [line for line in summary.splitlines() if line.strip()]


def test_summary_is_short_labelled_and_drops_boilerplate():
    summary = fact_summary(
        POLYU,
        title="Research Assistant",
        university="Hong Kong Polytechnic University",
        department="Department of Computing",
        project="Crypto-based secure federated computation for large-scale data collaboration",
        close_date="2026-11-15",
        date_type="review_start",
    )
    assert "University:" not in summary
    assert "- Dept: Department of Computing" in summary
    assert summary.startswith("- Dept:")
    assert "- Project:" in summary
    assert "- Role focus:" in summary
    assert "other duties" not in summary.lower()
    assert "equal opportunity" not in summary.lower()
    assert "not invited" not in summary.lower()
    assert "2766" not in summary
    assert "yijia.chang@polyu.edu.hk" in summary
    assert "- Review: 2026-11-15 (open until filled)" in summary
    assert "HK$20,000" in summary or "12 months" in summary
    assert len(summary) <= 600
    for line in _lines(summary):
        assert len(line) <= 200
        label = line.split(":", 1)[0].replace("- ", "")
        assert label in {"Dept", "Project", "Role focus", "Requirements", "Appointment", "Review", "Closing", "Contact"}


def test_prose_heading_and_job_ref_do_not_leak_into_the_summary():
    text = (
        "(Ref. 260916001)\n"
        "[Appointment period: six months]\n"
        "Duties of the position include conducting literature reviews, data cleaning and writing reports.\n"
        "Applicants should possess a bachelor degree in information systems."
    )
    summary = fact_summary(text, title="Research Assistant", department="Department of Information Systems")
    assert "260916001" not in summary
    assert "six months" in summary
    assert "conducting literature reviews" in summary
    assert not any(line.startswith("- Role focus: of the position") for line in _lines(summary))
    assert "bachelor" in summary.lower()


def test_title_is_not_repeated_at_the_start_of_the_role():
    title = "Research Assistant I/II in the Division of Epidemiology and Biostatistics"
    summary = fact_summary(HKU_DOUBLED, title=title, department="School of Public Health", close_date="2026-12-31")
    role = next(line for line in _lines(summary) if line.startswith("- Role focus:"))
    assert role.lower().count(title.lower()) == 0
    assert "Bachelor" in summary or "public health" in summary


def test_contact_without_email_is_a_name_not_a_phone():
    text = "Duties: Collect archival sources for the history project and draft a working paper.\nContact: Please call Professor Ada Chan on 3917 1234."
    summary = fact_summary(text, title="Research Assistant", department="Department of History")
    assert "3917" not in summary
    assert "Professor Ada Chan" in summary


def test_llm_rewrite_must_use_the_allowlist():
    good = "- Dept: Computing\n- Role focus: Run the federated-learning experiments.\n- Requirements: Honours degree in computer science"
    assert validate_llm_summary(good) == good

    duplicated = "- Dept: Computing\n- Dept: Computing\n- Role focus: Run the experiments."
    assert validate_llm_summary(duplicated).count("- Dept:") == 1

    assert validate_llm_summary("- CONTACT: a@b.c\n- Role focus: Work.\n- MAIN DUTIES: Work.") is None
    assert validate_llm_summary("- Role focus: Work.\n- Gender Identity: Non-binary") is None
    assert validate_llm_summary("- Dept: A\n- Dept: B\n- Role focus: Work.") is None
    assert validate_llm_summary("- Project Domain: Finance\n- Role focus: Work.") is None

    def rewrite(_prompt: str) -> str:
        return "- CONTACT: yijia.chang@polyu.edu.hk\n- Gender Identity: Non-binary\n- MAIN DUTIES: Literature"

    fallback = summarize(POLYU, title="Research Assistant", department="Department of Computing", model=rewrite)
    assert "Gender" not in fallback
    assert "CONTACT" not in fallback
    assert "- Dept: Department of Computing" in fallback


def test_corrupt_stored_summary_is_detected():
    assert summary_needs_repair("- Duties: Read papers.\n- MAIN DUTIES: Read papers.")
    assert summary_needs_repair("- Department: Public Health\n- Gender Identity: Non-binary")
    assert summary_needs_repair("- Dept: A\n- Dept: B")
    assert not summary_needs_repair("- Dept: History\n- Role focus: Read the archives.")
