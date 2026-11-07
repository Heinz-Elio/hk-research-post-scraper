"""Short extractive summaries for the job cards.

Each post becomes a few labelled lines: department, project, one sentence of
role focus, degree plus a few skills, appointment terms, a closing or review
date, and a contact (email, or a name when there is no email). Lines are
capped and boilerplate is dropped. The university is not repeated; the card
already shows the source.

A local model can rewrite that list, but only when it stays inside the label
allowlist. Anything else falls back to the extractive text.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

LINE_CAP = 180
TOTAL_CAP = 600

_CANONICAL = {
    "dept": "Dept",
    "project": "Project",
    "role focus": "Role focus",
    "requirements": "Requirements",
    "appointment": "Appointment",
    "closing": "Closing",
    "review": "Review",
    "contact": "Contact",
}
_ALLOWED = set(_CANONICAL)

_SECTION_HEADS = [
    ("Project", re.compile(r"^(?:project(?:\s+title)?|research\s+project)\b\s*:?\s*(.*)$", re.I)),
    ("Duties", re.compile(r"^(?:duties|responsibilities|job\s+duties|main\s+duties)\b\s*:?\s*(.*)$", re.I)),
    ("Requirements", re.compile(
        r"^(?:requirements?|qualifications?|entry\s+requirements|key\s+requirements)\b\s*:?\s*(.*)$",
        re.I,
    )),
    ("Contact", re.compile(r"^(?:contacts?|enquir(?:y|ies)|how\s+to\s+apply)\b\s*:?\s*(.*)$", re.I)),
    ("Salary", re.compile(r"^(?:salary|remuneration)\b\s*:?\s*(.*)$", re.I)),
    ("Appointment", re.compile(r"^(?:appointment(?:\s+period)?|duration)\b\s*:?\s*(.*)$", re.I)),
    ("Conditions", re.compile(r"^(?:conditions(?:\s+of\s+service)?|what\s+we\s+offer|benefits)\b\s*:?\s*(.*)$", re.I)),
]
_COMPOUND_HEAD = re.compile(
    r"^(?:and|&|/)\s+(?:duties|responsibilities|requirements?|qualifications?)\s*$",
    re.I,
)
_CONTACT_LINE = re.compile(r"\b(invited to contact|please contact|for enquir)", re.I)
_CLOSE_LINE = re.compile(r"^the closing date\b", re.I)
_END_LINE = re.compile(
    r"^(?:advertised\b|applications close\b|back to search results\b|whatsapp\b|facebook\b|linkedin\b)",
    re.I,
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().\-]{6,}\d)")
_SKIP_LINE = re.compile(
    r"^(apply now|printable version|skip to|posting date|share\b|menu\b|return to previous page)\b",
    re.I,
)
_META_LINE = re.compile(
    r"^(?:ref\.?|work type|department|categories|job title|job id|job description|job posting details|hong kong)\b",
    re.I,
)
_BOILER = re.compile(
    r"equal opportunit"
    r"|any other duties"
    r"|other duties as assigned"
    r"|duties as assigned"
    r"|personal data"
    r"|personal information"
    r"|privacy (?:policy|notice|statement)"
    r"|applicants? (?:who are )?not invited"
    r"|not be notified"
    r"|will not be acknowledged"
    r"|only shortlisted"
    r"|data protection ordinance"
    r"|without regard to"
    r"|we are an equal"
    r"|the university is an equal"
    r"|committed to equality"
    r"|all information on applicants"
    r"|fringe benefits"
    r"|medical and dental",
    re.I,
)
_BOILER_CLAUSE = re.compile(
    r"(?:,\s*)?(?:and\s+)?(?:perform\s+)?(?:any\s+)?other duties as assigned\b[^.;•]*"
    r"|\bfringe benefits\b[^.;•]*"
    r"|\bmedical and dental\b[^.;•]*",
    re.I,
)
_UNI_BLURB = re.compile(
    r"founded in \d{4}|established in \d{4}"
    r"|is a (?:modern|vibrant|dynamic|leading|world-class)"
    r"|research-led, and professionally"
    r"|about the university",
    re.I,
)
_REF_HEADER = re.compile(r"\(ref\.?\s*:?\s*\d+\)|\bto commence\b", re.I)
_DUTY_SENTENCE = re.compile(
    r"duties\b.{0,40}\binclude\b|"
    r"\bassist the\b|\bconduct(?:ing)?\b|"
    r"appointees? will|will be responsible|responsible for|"
    r"will (?:join|assist|participate|conduct|support|manage|perform|carry|contribute)",
    re.I,
)
_INSTITUTION = re.compile(
    r"\b(?:the university|this university|the school of|we embrace|we tailor|our students|"
    r"our programmes|professional education|learning environment|career paths|"
    r"faculty-driven|student-centred|student-centered)\b",
    re.I,
)
_DEMOGRAPHIC = re.compile(
    r"gender identity|ethnicit|marital status|religious affiliation|non-binary|housing assistance",
    re.I,
)
_BAD_LABEL = re.compile(
    r"gender|ethnicit|marital|religious|housing|non-binary|main duties|key requirements|"
    r"project domain|team environment|career path|privacy notice|university name",
    re.I,
)
_APOS = r"['’`]"
_DEGREE = re.compile(
    rf"((?:an?\s+)?(?:honours\s+|honor\s+)?"
    rf"(?:bachelor(?:{_APOS}s)?|master(?:{_APOS}s)?|doctoral|ph\.?\s*d\.?|m\.?\s*phil|mphil|doctorate)"
    rf"(?:\s+degree)?(?:\s+or above)?(?:\s+in\s+\S[^.;]{{0,140}})?"
    rf"|(?:an?\s+)?(?:honours\s+)?degree(?:\s+or above)?(?:\s+in\s+\S[^.;]{{0,140}})?)",
    re.I,
)
_SKILL = re.compile(
    r"(?:experience (?:in|with|of)|knowledge of|proficien\w* in|familiar with|"
    r"background in|skills? in|command of)\s+(\S.{3,90})",
    re.I,
)
_NAME = re.compile(
    r"\b((?:Prof(?:essor)?|Dr|Mr|Ms|Mrs)\.?\s+[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,2})"
)
_APPT_HINT = re.compile(
    r"month|year|contract|full-time|part-time|salary|remuneration|hk\$|¥|rmb|usd",
    re.I,
)


def _clean_line(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text or "")
    return re.sub(r"\s+", " ", text).strip(" \t:-")


def _trim_open_paren(text: str) -> str:
    """Drop a trailing fragment that starts a parenthesis or an 'e.g.'."""
    if text.count("(") > text.count(")"):
        cut = text.rfind("(")
        if cut > 12:
            text = text[:cut]
    text = re.sub(r"\s*\(?\s*(?:e\.g|i\.e)\.?\s*$", "", text, flags=re.I)
    return text.rstrip(" ,;:-.(")


def _cap(text: str, limit: int = LINE_CAP) -> str:
    text = _clean_line(_restore_abbrev(_protect_abbrev(text))).strip(" \t-;\"'")
    if len(text) <= limit and text.count("(") <= text.count(")"):
        return _trim_open_paren(text) if text.count("(") > text.count(")") else text
    window = _trim_open_paren(text[:limit])
    if len(window) < int(limit * 0.45):
        window = text[:limit]
    protected = _protect_abbrev(window)
    for sep in (". ", "; ", ", "):
        idx = protected.rfind(sep)
        if idx >= int(limit * 0.45):
            cut = _trim_open_paren(_restore_abbrev(protected[:idx]))
            if sep == ". ":
                return cut + "."
            return cut + "..."
    idx = window.rfind(" ")
    if idx >= int(limit * 0.4):
        return _trim_open_paren(window[:idx]) + "..."
    return _trim_open_paren(window) + "..."


_ABBREV = re.compile(
    r"\b(?:e\.g|i\.e|etc|Dr|Prof|Mr|Mrs|Ms|Jr|Sr|St|No|vs|Ph\.D|M\.Phil|M\.Sc|B\.Sc|B\.A|M\.A)\.",
    re.I,
)


def _protect_abbrev(text: str) -> str:
    return _ABBREV.sub(lambda match: match.group(0).replace(".", "\u0001"), text)


def _restore_abbrev(text: str) -> str:
    return text.replace("\u0001", ".")


def _sentences(text: str) -> List[str]:
    text = _clean_line(text)
    if not text:
        return []
    protected = _protect_abbrev(text)
    parts = re.split(r"(?<=[.!?])\s+|•|\u2022", protected)
    return [_restore_abbrev(part).strip(" \t-•") for part in parts if part.strip(" \t-•")]


def _scrub_sentence(sentence: str) -> str:
    """Drop boilerplate clauses without throwing away the rest of the sentence."""
    parts = re.split(r",\s*", sentence)
    kept = [part.strip(" .;") for part in parts if part.strip() and not _BOILER.search(part)]
    return ", ".join(part for part in kept if part)


def _useful(text: str) -> List[str]:
    found = []
    for sentence in _sentences(text):
        cleaned = _scrub_sentence(sentence)
        if len(cleaned) > 12:
            found.append(cleaned)
    return found


def _section_text(chunks: List[str]) -> str:
    parts: List[str] = []
    for part in chunks:
        part = _clean_line(part)
        if not part or _SKIP_LINE.match(part):
            continue
        if parts and re.match(r"^[a-z]{1,2}(?:,|\.|\s)", part) and parts[-1][-1].isalpha():
            parts[-1] = parts[-1] + part
        else:
            parts.append(part)
    text = re.sub(r"\s+([,.;:])", r"\1", " ".join(parts))
    return text.strip()


def _heading_match(line: str):
    """Return (label, rest) when ``line`` is a section heading, else None.

    A sentence such as "Duties of the position include ..." is not a heading.
    Headings are a label alone, or a label followed by a colon.
    """
    probe = line[1:-1].strip() if line.startswith("[") and line.endswith("]") else line
    for label, pattern in _SECTION_HEADS:
        hit = pattern.match(probe)
        if not hit:
            continue
        rest = (hit.group(1) or "").strip(" :")
        if _COMPOUND_HEAD.match(rest):
            rest = ""
        if ":" not in probe and rest:
            continue
        return label, rest
    return None


def _split_sections(text: str) -> Dict[str, str]:
    found: Dict[str, List[str]] = {}
    current = None
    last_plain = ""
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw.strip()
        if not line or _SKIP_LINE.match(line) or _CLOSE_LINE.match(line) or _END_LINE.match(line):
            if line and _END_LINE.match(line):
                current = None
            continue
        heading = _heading_match(line)
        if heading:
            label, rest = heading
            found.setdefault(label, [])
            if rest:
                # "Duration" on its own line, then "Appointment: 12 months".
                if label == "Appointment" and re.search(
                    r"duration|period|contract|appointment", last_plain or "", re.I
                ) and not re.search(r"\d{5,}", last_plain or ""):
                    found[label].append(f"{last_plain}: {rest}")
                else:
                    found[label].append(rest)
                current = None
            else:
                current = label
            continue
        dept = re.match(r"^department\s*:\s*(.+)$", line, re.I)
        if dept and "Department" not in found:
            found["Department"] = [dept.group(1)]
            current = None
            continue
        if _CONTACT_LINE.search(line):
            current = "Contact"
            found.setdefault("Contact", []).append(line)
            continue
        if current:
            found.setdefault(current, []).append(line)
        else:
            last_plain = line
            cleaned = _BOILER_CLAUSE.sub("", line).strip(" ,;")
            if len(cleaned) >= 40:
                found.setdefault("Prose", []).append(cleaned)
    sections = {}
    for label, parts in found.items():
        if label == "Appointment":
            bits = [_clean_line(part) for part in parts]
            joined = "; ".join(bit for bit in bits if bit and not _BOILER.search(bit))
        else:
            joined = _section_text(parts)
        if joined:
            sections[label] = joined
    return sections


def _strip_leading_title(text: str, title: str) -> str:
    if not text or not title:
        return text
    words = [re.escape(word) for word in re.split(r"\s+", _clean_line(title)) if word]
    if not words:
        return text
    pattern = r"\s+".join(words)
    cleaned = text
    for _ in range(2):
        updated = re.sub(
            r"^\s*" + pattern + r"\b[\s:.,\-–]*",
            "",
            cleaned,
            count=1,
            flags=re.I,
        )
        if updated == cleaned:
            break
        cleaned = updated
    return cleaned.strip()


def _narrative(text: str, title: str) -> str:
    kept: List[str] = []
    skip_value = False
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw.strip()
        if not line or _SKIP_LINE.match(line) or _CLOSE_LINE.match(line) or _END_LINE.match(line):
            continue
        if _BOILER.search(line) and len(_BOILER_CLAUSE.sub("", line).strip()) < 40:
            continue
        line = _BOILER_CLAUSE.sub("", line).strip(" ,;") or line
        if _META_LINE.match(line) or _CONTACT_LINE.search(line):
            skip_value = line.endswith(":") or ":" not in line
            continue
        if skip_value:
            skip_value = False
            if len(_clean_line(line)) < 90:
                continue
        probe = line[1:-1].strip() if line.startswith("[") and line.endswith("]") else line
        if _heading_match(line):
            break
        if re.match(r"^(?:how to apply|contacts?|enquir(?:y|ies))\b", probe, re.I):
            break
        if len(_clean_line(line)) < 40:
            continue
        kept.append(line)
    prose = _strip_leading_title(_section_text(kept), title)
    return prose


def _emails(text: str) -> List[str]:
    found = []
    for email in _EMAIL_RE.findall(text or ""):
        lowered = email.lower()
        if lowered.endswith((".png", ".jpg", ".gif")) or "example.com" in lowered or email.startswith("["):
            continue
        if email not in found:
            found.append(email)
    return found


def _contact_value(section: str, text: str) -> str:
    """Email only, or a person's name when the ad gives no email. Never a phone number."""
    for blob in (section, text):
        emails = _emails(blob or "")
        if emails:
            return emails[0]
    name = _NAME.search(section or "")
    if name:
        return name.group(1)
    return ""


_REF_FRAGMENT = re.compile(r"\(Ref\.?:", re.I)
_REQUIREMENT_SENTENCE = re.compile(
    r"applicants should|they should|should possess|should have|must (?:have|possess)|degree in|honours degree",
    re.I,
)


def _is_bad_role(sentence: str, title: str = "", department: str = "") -> bool:
    """University blurbs, reference headers, and title restatements are not duties."""
    if _UNI_BLURB.search(sentence) or _INSTITUTION.search(sentence):
        return True
    if re.match(r"applicants\b", sentence, re.I) and not _DUTY_SENTENCE.search(sentence):
        return True
    if re.search(r"competitive salary|medical benefits|annual leave|will be offered", sentence, re.I):
        return True
    if re.search(r"\b(?:HKMU|CUHK|HKUST|PolyU|the University)\b", sentence) and not _DUTY_SENTENCE.search(sentence):
        return True
    if re.search(r"is an advantage|would be an advantage|are welcome to apply", sentence, re.I):
        return True
    if _REQUIREMENT_SENTENCE.search(sentence) and not _DUTY_SENTENCE.search(sentence):
        return True
    if _REF_HEADER.search(sentence) and (
        re.search(r"to commence", sentence, re.I) or not _DUTY_SENTENCE.search(sentence)
    ):
        return True
    if _BOILER.search(sentence) and len(_BOILER_CLAUSE.sub("", sentence).strip()) < 40:
        return True
    stripped = _strip_leading_title(sentence, title)
    if department:
        stripped = _strip_leading_title(stripped, department)
    stripped = re.sub(r"\(ref\.?\s*:?\s*\d+\)", "", stripped, flags=re.I)
    if len(_clean_line(stripped)) < 20:
        return True
    return False


def _near_duplicate(left: str, right: str) -> bool:
    def norm(value: str) -> str:
        return re.sub(r"\W+", " ", value.lower()).strip()

    a, b = norm(left), norm(right)
    if not a or not b:
        return False
    if a == b or a.startswith(b[:48]) or b.startswith(a[:48]):
        return True
    return False


def _role_focus(duties: str, narrative: str, title: str, department: str = "") -> str:
    source = _strip_leading_title(duties or "", title) or narrative
    useful = [sentence for sentence in _useful(source) if not _is_bad_role(sentence, title, department)]
    chosen = [sentence for sentence in useful if _DUTY_SENTENCE.search(sentence)]
    # A doubled title leaves "of the School ... (Ref.: 123)." Prefer a real sentence.
    while len(chosen) > 1 and (
        len(chosen[0]) < 40
        or re.match(r"^(?:of|in|at|for)\b", chosen[0], re.I)
        or (_REF_FRAGMENT.search(chosen[0]) and len(chosen[0]) < 140)
    ):
        chosen = chosen[1:]
    if not chosen:
        return ""
    return _cap(chosen[0])


def _requirements_line(text: str) -> str:
    useful = [sentence for sentence in _useful(text) if not _UNI_BLURB.search(sentence)]
    blob = _BOILER_CLAUSE.sub(" ", " ".join(useful) if useful else _clean_line(text))
    blob = blob.replace("’", "'").replace("`", "'")
    if not blob or _BOILER.fullmatch(blob or ""):
        return ""
    degree_match = _DEGREE.search(blob)
    degree = ""
    if degree_match:
        degree = re.split(
            r"\s+(?:They|Applicants|The appointee)\b",
            degree_match.group(1),
            maxsplit=1,
            flags=re.I,
        )[0]
        degree = _cap(degree, 140)
    skills: List[str] = []
    for match in _SKILL.finditer(blob):
        skill = re.split(r"\s+(?:They|Applicants|The appointee)\b", match.group(1), maxsplit=1, flags=re.I)[0]
        skill = _cap(_clean_line(skill).strip(" ."), 70)
        if not skill or _BOILER.search(skill) or _UNI_BLURB.search(skill):
            continue
        if skill.lower().rstrip(".") in {item.lower().rstrip(".") for item in skills}:
            continue
        skills.append(skill)
        if len(skills) == 2:
            break
    parts = [part for part in (degree, *skills) if part]
    if parts:
        return _cap("; ".join(parts))
    for sentence in useful:
        if _REQUIREMENT_SENTENCE.search(sentence) and not _DUTY_SENTENCE.search(sentence):
            return _cap(sentence)
    return ""


def _appointment_line(appointment: str, salary: str) -> str:
    blob = " ".join(part for part in (appointment, salary) if part)
    if not blob:
        return ""
    picked = []
    for sentence in _sentences(blob):
        if _BOILER.search(sentence):
            continue
        if _APPT_HINT.search(sentence) or not picked:
            picked.append(sentence)
        if len(picked) == 2 and _APPT_HINT.search(" ".join(picked)):
            break
    chosen = [sentence for sentence in picked if _APPT_HINT.search(sentence)] or picked[:1]
    return _cap("; ".join(chosen))


def _date_line(close_date: str, date_type: str) -> Optional[Tuple[str, str]]:
    kind = (date_type or "").strip()
    if kind == "review_start" and close_date:
        return "Review", f"{close_date} (open until filled)"
    if kind == "open_until_filled":
        return "Closing", "Open until filled"
    if close_date:
        return "Closing", close_date
    return None


def _render(items: List[Tuple[str, str]]) -> str:
    lines = [f"- {label}: {value}" for label, value in items if value]
    text = "\n".join(lines)
    if len(text) <= TOTAL_CAP:
        return text
    shrinkable = {"Role focus", "Requirements", "Appointment", "Project"}
    for cap in (140, 100, 70):
        items = [(label, _cap(value, cap) if label in shrinkable else value) for label, value in items]
        lines = [f"- {label}: {value}" for label, value in items if value]
        text = "\n".join(lines)
        if len(text) <= TOTAL_CAP:
            return text
    while items and len(text) > TOTAL_CAP:
        # Drop the longest optional line until the card fits.
        optional = [i for i, (label, _) in enumerate(items) if label in ("Project", "Appointment", "Contact")]
        if not optional:
            break
        drop = max(optional, key=lambda i: len(items[i][1]))
        items.pop(drop)
        lines = [f"- {label}: {value}" for label, value in items if value]
        text = "\n".join(lines)
    return text


def fact_summary(
    text: str,
    *,
    title: str = "",
    university: str = "",
    department: str = "",
    project: str = "",
    close_date: str = "",
    url: str = "",
    date_type: str = "",
) -> str:
    """Short labelled lines taken from the scrape. Does not invent a contact or a date.

    ``university`` is accepted so older callers keep working. It is not printed:
    the source tag on the card already names the university.
    """
    del university, url  # the card shows the source; a URL is not a contact
    sections = _split_sections(text)
    department = _clean_line(department) or sections.get("Department", "")
    project = _clean_line(project) or sections.get("Project", "")
    if project and title and project.lower() == title.lower():
        project = ""
    narrative = ""
    if not sections.get("Duties") and not sections.get("Requirements"):
        narrative = _strip_leading_title(sections.get("Prose", ""), title) or _narrative(text, title)
    items: List[Tuple[str, str]] = []
    if department:
        items.append(("Dept", _cap(department, 120)))
    if project:
        items.append(("Project", _cap(project)))
    role = _role_focus(sections.get("Duties", ""), narrative, title, department)
    if department and role.lower().startswith(department.lower()):
        role = _strip_leading_title(role, department)
    requirements = _requirements_line(sections.get("Requirements", "") or narrative or sections.get("Duties", ""))
    if role and requirements and _near_duplicate(role, requirements):
        if _REQUIREMENT_SENTENCE.search(role) or _DEGREE.search(role):
            role = ""
        else:
            requirements = ""
    if role and _is_bad_role(role, title, department):
        role = ""
    if role:
        items.append(("Role focus", role))
    if requirements:
        items.append(("Requirements", requirements))
    appointment = _appointment_line(sections.get("Appointment", ""), sections.get("Salary", ""))
    if not appointment:
        appointment = _appointment_line(sections.get("Conditions", ""), "")
    if appointment:
        items.append(("Appointment", appointment))
    dated = _date_line(close_date, date_type)
    if dated:
        items.append(dated)
    contact = _contact_value(sections.get("Contact", ""), text)
    if contact and not _PHONE_RE.fullmatch(contact):
        items.append(("Contact", contact))
    if not items and title:
        items.append(("Role focus", _cap(title)))
    return _render(items)


def validate_llm_summary(text: str) -> Optional[str]:
    """Accept a model rewrite only when every line uses an allowed label once.

    Exact duplicate lines are dropped first. An unknown label, a repeated
    label, an ALL-CAPS label, or a demographic field rejects the whole rewrite.
    """
    raw = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not raw:
        return None
    deduped: List[str] = []
    seen_exact = set()
    for line in raw:
        if line in seen_exact:
            continue
        seen_exact.add(line)
        deduped.append(line)
    if _DEMOGRAPHIC.search("\n".join(deduped)):
        return None
    seen_labels = set()
    items: List[Tuple[str, str]] = []
    for line in deduped:
        if not line.startswith("- "):
            return None
        match = re.match(r"^-\s*([^:]+):\s*(.+)$", line)
        if not match:
            return None
        label = match.group(1).strip()
        value = match.group(2).strip()
        if len(label) >= 4 and label.isupper():
            return None
        key = label.lower()
        if key not in _ALLOWED or key in seen_labels:
            return None
        if key == "contact":
            emails = _emails(value)
            if emails:
                value = emails[0]
            elif _PHONE_RE.search(value):
                continue
        if not value:
            continue
        seen_labels.add(key)
        items.append((_CANONICAL[key], _cap(value)))
    if "role focus" not in seen_labels and "requirements" not in seen_labels:
        return None
    rendered = _render(items)
    return rendered or None


def summary_needs_repair(summary: str) -> bool:
    """True for stored LLM output that duplicated labels, shouted them, or invented fields."""
    if not summary:
        return False
    if _DEMOGRAPHIC.search(summary):
        return True
    labels = re.findall(r"(?m)^-\s*([^:]+):", summary)
    seen = set()
    for label in labels:
        stripped = label.strip()
        if len(stripped) >= 4 and stripped.isupper():
            return True
        if _BAD_LABEL.search(stripped):
            return True
        key = stripped.lower()
        if key in seen:
            return True
        seen.add(key)
    return False


def salvage_summary(summary: str) -> str:
    """Drop shouted, invented, or repeated lines from a stored summary and cap the rest."""
    items: List[Tuple[str, str]] = []
    seen = set()
    for line in (summary or "").splitlines():
        match = re.match(r"^-\s*([^:]+):\s*(.+)$", line.strip())
        if not match:
            continue
        label, value = match.group(1).strip(), match.group(2).strip()
        if len(label) >= 4 and label.isupper():
            continue
        if _BAD_LABEL.search(label) or _DEMOGRAPHIC.search(value) or _BAD_LABEL.search(value):
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        canonical = _CANONICAL.get(key, label)
        items.append((canonical, _cap(value)))
    return _render(items)


def _prompt(facts: str) -> str:
    return f"""Rewrite these job facts as a short bullet list.
Use only these labels: Dept, Project, Role focus, Requirements, Appointment, Closing, Review, Contact.
One fact per line, each line starting with "- ".
Do not invent fields, names, dates, or a University line. Do not use all-caps labels.

{facts}

List:"""


def summarize(
    text: str,
    title: str = "",
    university: str = "",
    department: str = "",
    project: str = "",
    close_date: str = "",
    url: str = "",
    date_type: str = "",
    model: Optional[Callable[[str], str]] = None,
) -> str:
    """Extractive summary. ``model`` may rewrite it; invalid output is discarded."""
    facts = fact_summary(
        text,
        title=title,
        university=university,
        department=department,
        project=project,
        close_date=close_date,
        url=url,
        date_type=date_type,
    )
    if model is None:
        return facts
    try:
        rewritten = validate_llm_summary(model(_prompt(facts)))
    except Exception as exc:
        print(f"  [summarize error] {exc}")
        return facts
    return rewritten or facts
