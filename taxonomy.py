"""
Controlled vocabulary and extractors for research posts.

min_degree is the lowest qualification the post asks for.
domains are searchable tags from a fixed list.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

DEGREE_RANK = {
    "unspecified": 0,
    "bachelor": 1,
    "master": 2,
    "doctor": 3,
}

DEGREE_LABELS = {
    "unspecified": "Unspecified",
    "bachelor": "Bachelor",
    "master": "Master",
    "doctor": "Doctor",
}

# id, display label, match phrases (lowercase)
DOMAIN_TAXONOMY: List[Tuple[str, str, List[str]]] = [
    (
        "ai-ml",
        "AI / ML",
        [
            "artificial intelligence",
            "machine learning",
            "deep learning",
            "neural network",
            "computer vision",
            "natural language processing",
            "nlp",
            "reinforcement learning",
            "generative ai",
            "large language model",
        ],
    ),
    (
        "computer-science",
        "Computer Science",
        [
            "computer science",
            "computing",
            "software",
            "programming",
            "informatics",
            "information science",
            "cybersecurity",
            "information security",
            "human-computer",
            "hci",
        ],
    ),
    (
        "data",
        "Data",
        [
            "data science",
            "data analytic",
            "big data",
            "data mining",
            "database",
            "information system",
            "bioinformatics",
        ],
    ),
    (
        "electronics",
        "Electronics",
        [
            "electronic",
            "electrical",
            "semiconductor",
            "vlsi",
            "circuit",
            "signal processing",
            "photonic",
            "photonics",
            "wireless",
            "5g",
            "6g",
            "telecommunications",
            "communication engineering",
        ],
    ),
    (
        "robotics",
        "Robotics",
        [
            "robotic",
            "automation",
            "control system",
            "autonomous",
            "mechatronic",
        ],
    ),
    (
        "mechanical",
        "Mechanical",
        [
            "mechanical",
            "aerospace",
            "aviation",
            "aeronautical",
            "thermal",
            "fluid",
            "manufacturing",
        ],
    ),
    (
        "civil",
        "Civil",
        [
            "civil engineering",
            "structural engineering",
            "geotechnical",
            "construction",
            "transportation engineering",
            "urban planning",
        ],
    ),
    (
        "biomedical",
        "Biomedical",
        [
            "biomedical",
            "bioengineering",
            "medical engineering",
            "clinical engineering",
            "rehabilitation engineering",
        ],
    ),
    (
        "life-science",
        "Life Science",
        [
            "biology",
            "biological",
            "life science",
            "biotech",
            "biotechnology",
            "genomic",
            "molecular biology",
            "microbiology",
            "neuroscience",
        ],
    ),
    (
        "chemistry",
        "Chemistry",
        [
            "chemistry",
            "chemical engineering",
            "chemical",
            "polymer",
        ],
    ),
    (
        "physics",
        "Physics",
        [
            "physics",
            "quantum",
            "optics",
            "nanotech",
            "nanotechnology",
        ],
    ),
    (
        "materials",
        "Materials",
        [
            "material",
            "metallurgy",
            "nanomaterial",
        ],
    ),
    (
        "environment",
        "Environment",
        [
            "environment",
            "environmental",
            "earth science",
            "geology",
            "climate",
            "sustainability",
            "ecology",
        ],
    ),
    (
        "math-stats",
        "Math / Stats",
        [
            "mathematics",
            "mathematical",
            "statistic",
            "actuarial",
            "operations research",
        ],
    ),
    (
        "industrial",
        "Industrial / Systems",
        [
            "industrial engineering",
            "systems engineering",
            "logistics",
            "supply chain",
        ],
    ),
]

DOMAIN_LABELS = {did: label for did, label, _ in DOMAIN_TAXONOMY}

_REQ_HEAD = re.compile(
    r"(requirement|qualif(?:ication|ied)|applicant(?:s)? (?:should|must|are)|"
    r"entry requirement|education(?:al)? requirement|minimum qualif)",
    re.I,
)
_INCIDENTAL = re.compile(
    r"supervis|doctoral student|phd student|ph\.?d\.? students|"
    r"towards a (?:ph\.?d|doctor)|enroll(?:ed|ing) in|"
    r"work(?:ing)? with (?:ph\.?d|doctoral)|pursue(?: a)? (?:ph\.?d|doctor)",
    re.I,
)

_DOCTOR = re.compile(
    r"\b(?:ph\.?d\.?|dphil|doctorate|doctoral|doctor of philosophy)\b",
    re.I,
)
_MASTER = re.compile(
    r"\b(?:master'?s?|mphil|m\.?\s*phil|msc|m\.?\s*sc|m\.a\.|meng|m\.eng)\b",
    re.I,
)
_BACHELOR = re.compile(
    r"\b(?:bachelor'?s?|bsc|b\.?\s*sc|b\.a\.|beng|b\.eng|undergraduate|"
    r"first degree|a degree in)\b",
    re.I,
)

_TITLE_DOCTOR = re.compile(
    r"post[\s-]?doc|research assistant professor|\brap\b|assistant professor",
    re.I,
)


def degree_rank(level: Optional[str]) -> int:
    if not level:
        return 0
    return DEGREE_RANK.get(level, 0)


def _window(text: str, start: int, end: int, pad: int = 48) -> str:
    return text[max(0, start - pad) : min(len(text), end + pad)]


def _requirements_slice(text: str) -> str:
    if not text:
        return ""
    m = _REQ_HEAD.search(text)
    if not m:
        return text[:4000]
    return text[m.start() : m.start() + 2500]


def _collect_levels(text: str) -> List[str]:
    found: List[str] = []
    for level, pat in (("doctor", _DOCTOR), ("master", _MASTER), ("bachelor", _BACHELOR)):
        for m in pat.finditer(text):
            ctx = _window(text, m.start(), m.end())
            if _INCIDENTAL.search(ctx):
                continue
            found.append(level)
    return found


def extract_min_degree(title: str, text: str = "") -> Tuple[str, int]:
    """
    Lowest academic requirement stated in the post.
    Alternatives ('Bachelor or Master') take the minimum.
    """
    title = title or ""
    body = _requirements_slice(text or "")
    combined = f"{title}\n{body}"

    levels = _collect_levels(combined)
    if not levels and text:
        levels = _collect_levels(text[:3500])

    if levels:
        min_level = min(levels, key=lambda lv: DEGREE_RANK[lv])
        return min_level, DEGREE_RANK[min_level]

    if _TITLE_DOCTOR.search(title):
        return "doctor", DEGREE_RANK["doctor"]

    return "unspecified", 0


def extract_domains(
    title: str = "",
    department: str = "",
    project: str = "",
    text: str = "",
) -> List[str]:
    hay = " ".join(
        part for part in (title, department, project, text[:4000]) if part
    ).lower()
    tags: List[str] = []
    for did, _label, phrases in DOMAIN_TAXONOMY:
        if any(p in hay for p in phrases):
            tags.append(did)
    return tags


def domain_label(domain_id: str) -> str:
    return DOMAIN_LABELS.get(domain_id, domain_id)


def extract_work_type(title: str, text: str = "") -> Optional[str]:
    combined = f"{title} {text}".lower()
    has_full = bool(re.search(r"\bfull[-\s]?time\b", combined))
    has_part = bool(re.search(r"\bpart[-\s]?time\b", combined))
    has_fractional = bool(re.search(r"\bfractional\b", combined))
    has_hourly = bool(re.search(r"\bhourly[-\s]?paid\b", combined))
    if has_full and has_part:
        return "Full-time/Part-time"
    if has_full:
        return "Full-time"
    if has_part or has_fractional or has_hourly:
        return "Part-time"
    return None


def plausible_department(name: Optional[str]) -> bool:
    if not name:
        return False
    name = name.strip()
    if not (5 < len(name) < 70):
        return False
    low = name.lower()
    if "[university" in low or " is seek" in low or "..." in name:
        return False
    return True


def extract_department(title: str, text: str = "") -> Optional[str]:
    combined = f"{title}\n{text}"
    patterns = [
        r"(?:Department|School|Faculty|Division|Centre|Center|Institute) of ([A-Z][^,\n\.]{5,60})",
        r"(?:in the |at the )?(Department|School|Faculty|Division) of ([A-Z][^,\n\.]{5,60})",
        r"([A-Z][A-Za-z& \-]{5,50} Department)",
        r"([A-Z][A-Za-z& \-]{5,50} School)",
    ]
    for pat in patterns:
        m = re.search(pat, combined)
        if m:
            name = m.group(1) if m.lastindex == 1 else (m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(0))
            name = re.split(r"\s+(?:at|is|who)\s+", name, maxsplit=1)[0]
            name = name.strip(" .,-")
            if plausible_department(name):
                return name
    return None


def enrich_classification(post: dict) -> dict:
    title = post.get("title") or ""
    text = post.get("content") or post.get("summary") or ""
    department = post.get("department") or ""
    project = post.get("project") or ""

    work_type = extract_work_type(title, text)
    if work_type:
        post["work_type"] = work_type
    else:
        post.setdefault("work_type", None)

    min_degree, rank = extract_min_degree(title, text)
    post["min_degree"] = min_degree
    post["degree_rank"] = rank
    post["degree_level"] = DEGREE_LABELS[min_degree] if min_degree != "unspecified" else None

    if not plausible_department(department):
        extracted = extract_department(title, text)
        if plausible_department(extracted):
            post["department"] = extracted
            department = extracted
        else:
            post.pop("department", None)
            department = ""

    post["domains"] = extract_domains(title, department, project, text)
    return post
