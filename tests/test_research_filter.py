"""Research-role filter: who is kept, and who stays out."""

from sources.base import is_research_related
from taxonomy import extract_domains


def test_research_roles_pass_outside_stem():
    kept = [
        ("Research Assistant", "Department of History"),
        ("Research Assistant", "Department of English"),
        ("Part-time Research Assistant", "Department of Educational Psychology"),
        ("Research Assistant", "The Nethersole School of Nursing"),
        ("Postdoctoral Fellow", "Department of Physics and Materials"),
        ("Post-doctoral Fellow", "Department of Clinical Oncology"),
        (
            "Postdoctoral Fellow(s) / Research Associate(s) (carrying the job title of 'Data Analyst')",
            "Department of Social Work",
        ),
        (
            "Full-time/Part-time Research Assistant(s) (AI research and development)",
            "English Language Teaching Unit",
        ),
        ("Research Assistant, Department of Biology", "Department of Biology"),
        ("Research Assistant Professor, Department of Physics", "Department of Physics"),
        ("Research Assistant Professor, Academy of Music", "Academy of Music"),
        ("Senior Research Assistant", "Department of English Language Education"),
        ("Research Officer, The Advanced Institute for Global Chinese Studies", ""),
        ("Part-time Assistant Research Officer, Department of Psychology", "Department of Psychology"),
        ("Data Analyst", ""),
        ("Research Analyst", "Department of History"),
        ("Data Scientist", "School of Public Health"),
        ("Half-time Project Associate", "School of Optometry"),
        ("Part-time Project Assistant", "Department of Logistics and Maritime Studies"),
        ("研究助理（机械结构工程师）", "Vice-President (Research) (VPR)"),
        ("研究助理（项目经理）", "Thrust of Smart Manufacturing"),
        ("博士后", "Thrust of Bioscience and Biomedical Engineering"),
        ("Postdoc (N&HS)", "School of Nursing and Health Sciences"),
        ("Part-Time Research Nurse", "Clinical Trials Centre"),
        (
            "Clinical Research Associate (at the rank of Technical Officer/Research Assistant I/II)",
            "Clinical Trials Centre",
        ),
        (
            "Project Officer / Assistant Project Officer, Hong Kong and South China Historical Research Programme",
            "",
        ),
        ("Technical Officer（NICE 光电工程师）", "Novel IC Exploration Facility (NICE)"),
        ("技术助理（BioCRF）质谱色谱方向", "Biosciences Central Research Facility (GZ)"),
        ("Senior Scientist (Clinical Research)", "School of Chinese Medicine"),
        ("Research Associate Laboratory Manager", "Division of Life Science"),
        ("Research Assistant / Research Administrative Assistant", "Department of Computing"),
        ("Scientific Officer, Advanced Life Sciences and Mass Spectrometry Laboratory", "Advanced Life Sciences Laboratory"),
    ]
    for title, dept in kept:
        assert is_research_related(title, department=dept), title


def test_admin_and_non_research_titles_are_excluded():
    dropped = [
        ("Executive Officer", "Registry"),
        ("Financial Analyst", "Finance Office"),
        ("Executive Assistant (at the rank of Clerk II)", "Faculty of Engineering"),
        ("Clerk II (holding the functional title of Executive Assistant)", "Medicine"),
        ("Administrative Officer (Research and Development)", "Society Hub"),
        ("Senior Manager (External Grants), Research Office", "Research Office"),
        ("Manager (Research Impact and Assessment), Research Office", "Research Office"),
        ("Senior Executive Officer, Research Postgraduate Programme", ""),
        ("Senior Finance Manager / Finance Manager (Special Projects)", "Finance Office"),
        ("Library Assistant", ""),
        ("Teaching Assistant", "Faculty of Engineering"),
        ("Assistant Professor (Information Systems)", "School of Business"),
        ("Systems Analyst (Application Development & Support)", "School of Continuing Education"),
        ("Senior Analyst Programmer (Student Information Systems)", "Office of Information Technology"),
        ("Programme Officer, Division of Artificial Intelligence", "Division of Artificial Intelligence"),
        ("Assistant Programme Officer, Faculty of Business", "Faculty of Business"),
        (
            "Project Co-ordinator II (carrying the job title of 'Assistant Manager, Career Services')",
            "Office of Co-operative Education Programme",
        ),
        ("Project Co-ordinator II", "School of Accountancy"),
        ("Project Assistant II", "Office of Admissions and Financial Aid"),
        ("Project Assistant II", "United College"),
        ("Project Associate (Administration)", "Department of Land Surveying and Geospatial Science"),
        ("实验室设施维护工程师", "Biosciences Central Research Facility"),
        ("项目工程师", "Low Altitude Systems and Economy Research Institute"),
        ("Technical Officer 技术专员（产业发展、知识转移与教育培训）", "Low Altitude Systems and Economy Research Institute"),
        ("Technical Officer", "Hong Kong Science and Technology Parks"),
        ("Technical Officer (Project Management)", "Section of Smart Campus Management"),
        ("Frontend Developer 前端工程师", "Information Technology and Data Intelligence Department"),
        (
            "Coordinator, Communication and Public Engagement (at the rank of Technical Officer/ Research Assistant I/II)",
            "Clinical Trials Centre",
        ),
        ("行政专员（AI）", "Office of Student Affairs"),
        ("Laboratory Manager (at the rank of Technical Manager)", "Faculty of Medicine"),
        ("Project Assistant (at the rank of Clerk)", "Department of Ophthalmology"),
        ("Project Assistant (at the rank of Clerk I/II)", "Department of Computing"),
        ("Research Assistant (at the rank of Clerk II)", "Department of History"),
        ("Clerk I/II", "Faculty of Arts"),
        ("Clerical Officer", "Registry"),
        ("Senior Clerk", "Department of Physics"),
        ("文員", "Department of Computing"),
        ("文员", ""),
        ("文書主任", "Faculty of Engineering"),
        ("Project Executive（文員職級）", "School of Nursing"),
    ]
    for title, dept in dropped:
        assert is_research_related(title, department=dept) is False, title


def test_clerk_grade_in_the_advertisement_is_excluded():
    assert is_research_related(
        "Research Assistant",
        department="Department of Computing",
        description="The appointee will serve at the rank of Clerk II for twelve months.",
    ) is False
    assert is_research_related(
        "Project Associate",
        department="Department of Social Work",
        description="Appointment will be on the Clerk grade.",
    ) is False
    assert is_research_related(
        "研究助理",
        department="Thrust of Smart Manufacturing",
        description="以文員職級聘任，協助實驗室工作。",
    ) is False
    # A mention of someone else's clerk duties is not this post's grade.
    assert is_research_related(
        "Research Assistant",
        department="Department of History",
        description="Liaise with the departmental clerk about room bookings and archives.",
    )


def test_domain_tags_ignore_incidental_words():
    vet = (
        "Experience in bioinformatics, e.g. Bowtie2, would be an advantage. "
        "Medical and dental consultations at the campus clinic."
    )
    domains = extract_domains(
        "Postdoctoral Fellow/Research Assistant",
        "Department of Veterinary Clinical Sciences",
        "One-health Pathogen Surveillance",
        vet,
    )
    assert "computer-science" not in domains
    assert "data" in domains
    assert "health" in domains

    social = (
        "Excellent academic knowledge of research methods, statistics and SPSS. "
        "The appointee will be responsible for preparing research materials."
    )
    domains = extract_domains(
        "Research Assistant",
        "Department of Social and Behavioural Sciences",
        "",
        social,
    )
    assert "math-stats" not in domains
    assert "materials" not in domains

    assert "math-stats" in extract_domains(
        "Research Assistant",
        "Department of Statistics",
        "",
        "Knowledge of statistics and SPSS is required.",
    )
    assert "materials" in extract_domains(
        "Research Assistant",
        "Department of Physics and Materials",
        "",
        "",
    )
    assert "environment" not in extract_domains(
        "Research Assistant",
        "Department of Social and Behavioural Sciences",
        "",
        "A supportive work environment and a changing environment on campus.",
    )
    assert "environment" in extract_domains(
        "Research Assistant",
        "Institute for the Environment",
        "",
        "",
    )
    assert "health" not in extract_domains(
        "Research Assistant",
        "Department of Computer Science",
        "",
        "Fringe benefits include medical and dental consultations at the campus clinic.",
    )
    assert "ai-ml" in extract_domains(
        "Postdoctoral Fellow (AI Infrastructure)",
        "Department of Information Engineering",
        "",
        "",
    )
