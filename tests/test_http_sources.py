"""Fetch and parse tests for the five HTTP career APIs.

Network calls are mocked. Fixtures follow responses captured on 2026-11-05.
"""

from unittest.mock import patch

from sources.base import ListingUnchanged, is_research_related
from sources.hkbu import _closing_date, _department, _detail_url, scrape as scrape_hkbu
from sources.hkmu import scrape as scrape_hkmu
from sources.hkust_gz import _close_date, scrape as scrape_gz
from sources.lingnan import scrape as scrape_lingnan
from sources.taleo import parse_detail_html, search_jobs
from sources.cuhk import scrape as scrape_cuhk


def _taleo_detail(fields, values):
    """Minimal Taleo detail page: values, then the reqlistitem name list."""
    chunks = ["descRequisition", *values, "descRequisition.size", "1"]
    names = "','".join(fields)
    return "!|!".join(chunks) + f"\n'{names}'\n"


CUHK_FIELDS = [
    "reqlistitem.title",
    "reqlistitem.contestnumber",
    "reqlistitem.description",
    "reqlistitem.jobfield",
    "reqlistitem.organization",
    "reqlistitem.unpostingdate",
]
HKMU_FIELDS = [
    "reqlistitem.description",
    "reqlistitem.title",
    "reqlistitem.contestnumber",
    "reqlistitem.organization",
    "reqlistitem.unpostingdate",
]


def test_taleo_detail_cuhk_date_and_description():
    html = _taleo_detail(
        CUHK_FIELDS,
        [
            "Research Assistant",
            "260001UX",
            "!*!%3Cp%3EApplicants should have a degree in computer science.%3C/p%3E",
            "Research Posts",
            "Department of Computer Science and Engineering",
            "Nov 30, 2026",
        ],
    )
    parsed = parse_detail_html(html)
    assert parsed["title"] == "Research Assistant"
    assert parsed["contest_no"] == "260001UX"
    assert parsed["organization"] == "Department of Computer Science and Engineering"
    assert "computer science" in parsed["description"]
    assert "<p>" not in parsed["description"]
    assert parsed["unposting_date"] == "Nov 30, 2026"


def test_taleo_detail_hkmu_field_order_and_ongoing():
    html = _taleo_detail(
        HKMU_FIELDS,
        [
            "!*!%3Cp%3EThe School of Nursing and Health Studies invites applications.%3C/p%3E",
            "Research Assistant I/II (R7069) (N%26HS)",
            "26002HE",
            "School of Nursing and Health Sciences",
            "Ongoing",
        ],
    )
    parsed = parse_detail_html(html)
    assert parsed["title"] == "Research Assistant I/II (R7069) (N&HS)"
    assert parsed["contest_no"] == "26002HE"
    assert "Health Studies" in parsed["description"]
    assert parsed["unposting_date"] == "Ongoing"


def test_taleo_search_pages_until_total_count():
    pages = {
        1: {
            "requisitionList": [
                {"contestNo": "A1", "column": ["A1", "Research Assistant", "Dept of Computer Science"]}
            ],
            "pagingData": {"totalCount": 2, "pageSize": 1, "currentPageNo": 1},
        },
        2: {
            "requisitionList": [
                {"contestNo": "A2", "column": ["A2", "Clerk", "Registry"]}
            ],
            "pagingData": {"totalCount": 2, "pageSize": 1, "currentPageNo": 2},
        },
    }

    def fake(method, url, **kwargs):
        assert method == "POST"
        assert "portal=8115020119" in url
        assert kwargs["extra_headers"]["tz"] == "GMT+08:00"
        return pages[kwargs["json_body"]["pageNo"]]

    with patch("sources.taleo.api_request", side_effect=fake), patch("sources.taleo.time.sleep"):
        rows = search_jobs("https://cuhk.taleo.net", "8115020119")
    assert [row["contestNo"] for row in rows] == ["A1", "A2"]


def test_taleo_search_failure_is_none():
    with patch("sources.taleo.api_request", return_value=None):
        assert search_jobs("https://cuhk.taleo.net", "8115020119") is None


def test_cuhk_scrape_keeps_research_roles_in_any_department():
    rows = [
        {"contestNo": "260001CS", "column": ["260001CS", "Research Assistant", "Department of Computer Science and Engineering"]},
        {"contestNo": "260001HX", "column": ["260001HX", "Executive Officer", "Registry"]},
        {"contestNo": "260001HS", "column": ["260001HS", "Research Assistant", "Department of History"]},
    ]
    detail = {
        "title": "Research Assistant",
        "description": "Duties include software experiments.",
        "unposting_date": "Nov 30, 2026",
        "organization": "Department of Computer Science and Engineering",
    }
    with patch("sources.cuhk.search_jobs", return_value=rows), \
         patch("sources.cuhk.fetch_detail", return_value=detail), \
         patch("sources.cuhk.same_listing", return_value=False), \
         patch("sources.cuhk.finish_listing"), \
         patch("sources.cuhk.time.sleep"):
        posts = scrape_cuhk()
    ids = {post["id"] for post in posts}
    assert ids == {"CUHK_260001CS", "CUHK_260001HS"}
    post = next(item for item in posts if item["id"] == "CUHK_260001CS")
    assert post["source"] == "CUHK"
    assert post["department"] == "Department of Computer Science and Engineering"
    assert post["close_date"] == "2026-11-30"
    assert post["url"].endswith("jobdetail.ftl?job=260001CS&lang=en")
    assert "software experiments" in post["content"]


def test_cuhk_unchanged_listing_skips_details():
    rows = [
        {"contestNo": "260001CS", "column": ["260001CS", "Research Assistant", "Department of Computer Science and Engineering"]},
    ]
    with patch("sources.cuhk.search_jobs", return_value=rows), \
         patch("sources.cuhk.fetch_detail") as fetch_detail, \
         patch("sources.cuhk.same_listing", return_value=True), \
         patch("sources.cuhk.time.sleep"):
        result = scrape_cuhk()
    assert isinstance(result, ListingUnchanged)
    fetch_detail.assert_not_called()


def test_hkmu_passes_department_into_the_stem_check():
    assert is_research_related("Research Assistant I/II (R7069) (N&HS)")
    assert is_research_related(
        "Research Assistant I/II (R7069) (N&HS)",
        department="School of Nursing and Health Sciences",
    )
    assert is_research_related("Postdoc (N&HS)", department="School of Nursing and Health Sciences")

    rows = [
        {
            "contestNo": "26002HE",
            "column": [
                "Research Assistant I/II (R7069) (N&HS)",
                "School of Nursing and Health Sciences",
                "19/Nov/2026",
            ],
        },
        {
            "contestNo": "26002EW",
            "column": ["Officer (FO)", "Finance Office", "10/Nov/2026"],
        },
    ]
    detail = {
        "title": "Research Assistant I/II (R7069) (N&HS)",
        "description": "Support nursing science studies.",
        "unposting_date": "19/Nov/2026, 11:59:00 PM",
        "organization": "School of Nursing and Health Sciences",
    }
    with patch("sources.hkmu.search_jobs", return_value=rows), \
         patch("sources.hkmu.fetch_detail", return_value=detail), \
         patch("sources.hkmu.same_listing", return_value=False), \
         patch("sources.hkmu.finish_listing"), \
         patch("sources.hkmu.time.sleep"):
        posts = scrape_hkmu()
    assert len(posts) == 1
    assert posts[0]["id"] == "HKMU_26002HE"
    assert posts[0]["close_date"] == "2026-11-19"
    assert posts[0]["department"] == "School of Nursing and Health Sciences"


def test_hkmu_listing_date_used_when_detail_fails():
    rows = [
        {
            "contestNo": "26002DK",
            "column": ["Postdoc (N&HS)", "School of Nursing and Health Sciences", "06/Nov/2026"],
        }
    ]
    with patch("sources.hkmu.search_jobs", return_value=rows), \
         patch("sources.hkmu.fetch_detail", return_value=None), \
         patch("sources.hkmu.same_listing", return_value=False), \
         patch("sources.hkmu.finish_listing"), \
         patch("sources.hkmu.time.sleep"):
        posts = scrape_hkmu()
    assert posts[0]["close_date"] == "2026-11-06"
    assert posts[0]["content"] == ""


def test_hkbu_department_and_closing_date():
    assert _department(
        "Research Assistant, Department of Computer Science",
        "ignored",
    ) == "Department of Computer Science"
    assert _department(
        "Technical Officer",
        "This position sits under the Department of Physics at our campus.",
    ) == "Department of Physics at our campus"
    assert _closing_date(None, "Review of applications is ongoing until the position is filled.") is None
    assert _closing_date(None, "Closing date: 15 December 2026. Please apply online.") == "2026-12-15"
    # Milliseconds are stripped, then the shared parser converts the instant to Hong Kong time.
    assert _closing_date("2026-12-01T16:00:00.000+00:00", "") == "2026-12-02"
    assert 'Id="26270211"' in _detail_url("26270211")


def test_hkbu_scrape_filters_client_side_and_reads_detail():
    listing = {
        "items": [
            {
                "TotalJobsCount": 2,
                "requisitionList": [
                    {
                        "Id": "26270211",
                        "Title": "Research Assistant, Department of Computer Science",
                        "ShortDescriptionStr": "This position sits under the Department of Computer Science.",
                        "PostingEndDate": None,
                    },
                    {
                        "Id": "9",
                        "Title": "Library Assistant",
                        "ShortDescriptionStr": "Shelving.",
                        "PostingEndDate": None,
                    },
                ],
            }
        ]
    }
    detail = {
        "items": [
            {
                "Title": "Research Assistant, Department of Computer Science",
                "ExternalPostedEndDate": None,
                "ExternalDescriptionStr": "<p>Closing date: 15 December 2026.</p><p>Build data tools.</p>",
                "ShortDescriptionStr": "This position sits under the Department of Computer Science.",
            }
        ]
    }

    def fake(method, url, **kwargs):
        assert method == "GET"
        if "recruitingCEJobRequisitions" in url:
            assert "siteNumber=CX_1" in url
            assert "keyword" not in url
            return listing
        assert "recruitingCEJobRequisitionDetails" in url
        return detail

    with patch("sources.hkbu.api_request", side_effect=fake), \
         patch("sources.hkbu.same_listing", return_value=False), \
         patch("sources.hkbu.finish_listing"), \
         patch("sources.hkbu.time.sleep"):
        posts = scrape_hkbu()
    assert len(posts) == 1
    post = posts[0]
    assert post["id"] == "HKBU_26270211"
    assert post["close_date"] == "2026-12-15"
    assert post["department"] == "Department of Computer Science"
    assert post["url"].endswith("/sites/hkbu/job/26270211")
    assert "Build data tools" in post["content"]
    assert "<p>" not in post["content"]


LINGNAN_HTML = """
<script>csod.context={"token":"header.payload.sig","endpoints":{"cloud":"https://uk.api.csod.com/"}};</script>
"""


def test_lingnan_uses_research_category_and_stem_filter():
    search = {
        "data": {
            "totalCount": 3,
            "requisitions": [
                {
                    "requisitionId": 3078,
                    "displayJobTitle": "Senior Research Officer, Division of Science",
                    "postingExpirationDate": "-",
                    "externalDescription": "Manage the science laboratories.",
                },
                {
                    "requisitionId": 3093,
                    "displayJobTitle": "Assistant Programme Officer, Faculty of Business",
                    "postingExpirationDate": "-",
                    "externalDescription": "Programme administration.",
                },
                {
                    "requisitionId": 3086,
                    "displayJobTitle": "Part-time Assistant Research Officer, Department of Psychology",
                    "postingExpirationDate": "-",
                    "externalDescription": "Run computer experiments for the psychology lab.",
                },
            ],
        }
    }
    bodies = []

    def fake(method, url, **kwargs):
        if method == "GET":
            assert "lingnan.csod.com" in url
            assert kwargs.get("pause") == 10
            return LINGNAN_HTML
        bodies.append(kwargs["json_body"])
        assert kwargs["extra_headers"]["Authorization"] == "Bearer header.payload.sig"
        assert "uk.api.csod.com/rec-job-search/external/jobs" in url
        return search

    with patch("sources.lingnan.api_request", side_effect=fake), \
         patch("sources.lingnan.same_listing", return_value=False), \
         patch("sources.lingnan.finish_listing"):
        posts = scrape_lingnan()
    assert bodies[0]["customFieldDropdowns"] == [{"id": 151, "options": [103]}]
    titles = {post["title"] for post in posts}
    assert "Senior Research Officer, Division of Science" in titles
    assert "Part-time Assistant Research Officer, Department of Psychology" in titles
    assert all("Programme Officer" not in title for title in titles)
    science = next(post for post in posts if post["id"] == "Lingnan_3078")
    assert science["department"] == "Division of Science"
    assert science["close_date"] is None
    assert science["url"].endswith("/requisition/3078?c=lingnan")
    assert "laboratories" in science["content"]


def test_hkust_gz_chinese_titles_dates_and_detail_url():
    assert is_research_related("研究助理（嵌入式开发工程师）", department="Vice-President (Research) (VPR)")
    assert is_research_related("研究助理（AI 算法工程师）")
    assert is_research_related("实验室研究助理（BSBE）", department="Thrust of Bioscience and Biomedical Engineering")
    assert is_research_related("技术助理（BioCRF）质谱色谱方向", department="Biosciences Central Research Facility (GZ)")
    assert is_research_related("博士后", department="Thrust of Bioscience and Biomedical Engineering")
    assert is_research_related("研究助理（项目经理）", department="Thrust of Smart Manufacturing")
    assert is_research_related("Research Assistant", department="Department of History")
    assert is_research_related("Research Assistant", department="Department of Computer Science")
    assert is_research_related(
        "Research Assistant (AI research and development)",
        department="English Language Teaching Unit",
    )
    assert is_research_related(
        "Postdoctoral Fellow(s) / Research Associate(s) (carrying the job title of 'Data Analyst')",
        department="Department of Social Work",
    )
    assert is_research_related("Executive Officer", department="Registry") is False
    assert is_research_related("Administrative Officer (Research and Development)") is False

    assert _close_date("3000-01-02 07:59:59") is None
    assert _close_date("2027-01-01 07:59:59") == "2027-01-01"
    assert _close_date("") is None

    listing = {
        "code": 0,
        "data": [
            {
                "id": "1320",
                "jobid": "6727",
                "postNameCh": "研究助理（机械结构工程师）",
                "enPostDept": "Vice-President (Research) (VPR)",
                "hubName": "ADMINISTRATIVE SERVICE DEPARTMENTS",
                "offlineDate": "2027-01-01 07:59:59",
            },
            {
                "id": "675",
                "jobid": "6069",
                "postNameCh": "Administrative Officer (Recruitment and Admissions)",
                "enPostDept": "Office of Student Affairs (OSA)",
                "hubName": "ADMINISTRATIVE SERVICE DEPARTMENTS",
                "offlineDate": "3000-01-02 07:59:59",
            },
            {
                "id": "1411",
                "jobid": "6900",
                "postNameCh": "研究助理（项目经理）",
                "enPostDept": "Thrust of Smart Manufacturing",
                "hubName": "Systems Hub",
                "offlineDate": "2027-04-01 07:59:59",
            },
            {
                "id": "74",
                "jobid": "5001",
                "postNameCh": "Post-doctoral Fellow",
                "enPostDept": "Thrust of Data Science and Analytics",
                "hubName": "Information Hub",
                "offlineDate": "3000-01-02 07:59:59",
            },
        ],
    }
    details = {
        "1320": {
            "code": 0,
            "data": {
                "postNameCh": "研究助理（机械结构工程师）",
                "enPostDept": "Vice-President (Research) (VPR)",
                "offlineDate": "2027-01-01 07:59:59",
                "jobPostingDetail": {"content": "<p>Design mechanical prototypes.</p>"},
                "qualificationCandidates": {"content": ""},
            },
        },
        "74": {
            "code": 0,
            "data": {
                "postNameCh": "Post-doctoral Fellow",
                "enPostDept": "Thrust of Data Science and Analytics",
                "offlineDate": "3000-01-02 07:59:59",
                "jobPostingDetail": {"content": "<p>PhD in computer science.</p>"},
            },
        },
        "1411": {
            "code": 0,
            "data": {
                "postNameCh": "研究助理（项目经理）",
                "enPostDept": "Thrust of Smart Manufacturing",
                "offlineDate": "2027-04-01 07:59:59",
                "jobPostingDetail": {"content": "<p>Coordinate the manufacturing study.</p>"},
            },
        },
    }

    def fake(method, url, **kwargs):
        assert method == "GET"
        if url.endswith("/career/list"):
            return listing
        record_id = url.rstrip("/").split("/")[-1]
        assert record_id in details
        return details[record_id]

    with patch("sources.hkust_gz.api_request", side_effect=fake), \
         patch("sources.hkust_gz.same_listing", return_value=False), \
         patch("sources.hkust_gz.finish_listing"), \
         patch("sources.hkust_gz.time.sleep"):
        posts = scrape_gz()
    by_id = {post["id"]: post for post in posts}
    assert set(by_id) == {"HKUST-GZ_6727", "HKUST-GZ_5001", "HKUST-GZ_6900"}
    engineer = by_id["HKUST-GZ_6727"]
    assert engineer["title"] == "研究助理（机械结构工程师）"
    assert engineer["close_date"] == "2027-01-01"
    assert engineer["url"] == "https://career.hkust-gz.edu.cn/en/job-detail?jobId=1320"
    assert "mechanical prototypes" in engineer["content"]
    fellow = by_id["HKUST-GZ_5001"]
    assert fellow["close_date"] is None
    assert "computer science" in fellow["content"]


def test_search_failure_returns_empty_without_touching_the_listing_hash():
    with patch("sources.cuhk.search_jobs", return_value=None), \
         patch("sources.cuhk.finish_listing") as finish:
        assert scrape_cuhk() == []
        finish.assert_not_called()


def test_modules_do_not_require_playwright():
    import sources.cuhk as cuhk
    import sources.hkbu as hkbu
    import sources.hkmu as hkmu
    import sources.hkust_gz as hkust_gz
    import sources.lingnan as lingnan

    for module in (cuhk, hkbu, hkmu, hkust_gz, lingnan):
        assert not hasattr(module, "sync_playwright")
        source = open(module.__file__, encoding="utf-8").read()
        assert "playwright" not in source.lower()

