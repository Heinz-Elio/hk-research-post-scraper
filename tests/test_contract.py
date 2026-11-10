"""Contract length from appointment lines in the current posts."""

from contract import attach_contract, contract_overlaps, parse_contract


def test_lengths_from_real_appointment_lines():
    six = parse_contract("of appointment: 6 months")
    assert six["contract_months"] == 6
    assert six["contract_months_max"] == 6
    assert six["contract_renewable"] is None

    years = parse_contract("1 to 2 years (renewable)")
    assert (years["contract_months"], years["contract_months_max"]) == (12, 24)
    assert years["contract_renewable"] is True

    assert parse_contract("thirteen months")["contract_months"] == 13
    span = parse_contract("nine to thirteen months")
    assert (span["contract_months"], span["contract_months_max"]) == (9, 13)

    fixed = parse_contract(
        "The appointment will be expected to commence on 19th October, 2026 "
        "on a three-month fixed-term basis, with the possibility of renewal "
        "subject to satisfactory performance and funding availability."
    )
    assert fixed["contract_months"] == 3
    assert fixed["contract_renewable"] is True

    duration = parse_contract(
        "(Duration: 3 – 6 months, renewable): 6 months to 1 year (starting in Fall 2025)"
    )
    assert (duration["contract_months"], duration["contract_months_max"]) == (3, 12)
    assert duration["contract_renewable"] is True

    up_to = parse_contract("The appointment is up to 2 years.")
    assert up_to["contract_months"] is None
    assert up_to["contract_months_max"] == 24

    wide = parse_contract("each for twelve to thirty-six months")
    assert (wide["contract_months"], wide["contract_months_max"]) == (12, 36)


def test_salary_and_experience_are_not_a_contract():
    blank = parse_contract("Negotiable based on qualifications and experience.")
    assert blank["contract_months"] is None
    assert blank["contract_months_max"] is None
    assert parse_contract("Applicants should have two years of experience in a laboratory.")[
        "contract_months"
    ] is None
    # A duration next to an experience sentence is still read when it is the appointment.
    kept = parse_contract(
        "Salary will be commensurate with qualifications and experience. "
        "(Duration: 2 years, renewable)"
    )
    assert kept["contract_months"] == 24
    assert kept["contract_renewable"] is True


def test_buckets_and_missing_fields():
    post = {
        "title": "Research Assistant",
        "summary": "- Appointment: twelve months\n- Requirements: two years of experience.",
    }
    attach_contract(post)
    assert post["contract_months"] == 12
    assert contract_overlaps(post, "6-12")
    assert not contract_overlaps(post, "le6")
    assert not contract_overlaps(post, "unknown")

    unknown = {"title": "Research Assistant", "summary": "- Dept: History"}
    attach_contract(unknown)
    assert "contract_months" not in unknown
    assert contract_overlaps(unknown, "unknown")

    ranged = {"contract_months": 6, "contract_months_max": 12}
    assert contract_overlaps(ranged, "6-12")
    assert not contract_overlaps(ranged, "le6")
    assert contract_overlaps({"contract_months": 6, "contract_months_max": 6}, "le6")
    assert contract_overlaps({"contract_months": 36, "contract_months_max": 36}, "gt24")
