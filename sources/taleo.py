"""Oracle Taleo career-section REST client.

CUHK and HKMU (and, later, other Taleo tenants such as the Airport
Authority) publish the job table through the same search endpoint.
Column order differs by tenant; callers map ``column`` themselves.
The detail page is still HTML, but the description and unposting date
are in the static ``!|!`` payload, so no browser is required.
"""

from __future__ import annotations

import re
import time
from typing import List, Optional
from urllib.parse import quote, unquote

from sources.base import REQUEST_DELAY, api_request, html_to_text

_MAX_PAGES = 40

_SEARCH_BODY = {
    "multilineEnabled": False,
    "sortingSelection": {"sortBySelectionParam": "3", "ascendingSortingOrder": "false"},
    "fieldData": {"fields": {"KEYWORD": "", "LOCATION": "", "CATEGORY": ""}, "valid": True},
    "filterSelectionParam": {
        "searchFilterSelections": [
            {"id": "POSTING_DATE", "selectedValues": []},
            {"id": "LOCATION", "selectedValues": []},
            {"id": "JOB_FIELD", "selectedValues": []},
        ]
    },
    "advancedSearchFiltersSelectionParam": {"searchFilterSelections": []},
}

_FIELD_LIST = re.compile(
    r"((?:reqlistitem\.[A-Za-z0-9_]+)(?:','reqlistitem\.[A-Za-z0-9_]+)+)"
)


def search_url(host: str, portal: str, lang: str = "en") -> str:
    return f"{host}/careersection/rest/jobboard/searchjobs?lang={lang}&portal={portal}"


def detail_url(host: str, section: str, contest_no: str, lang: str = "en") -> str:
    job = quote(str(contest_no).strip(), safe="")
    return f"{host}/careersection/{section}/jobdetail.ftl?job={job}&lang={lang}"


def search_jobs(host: str, portal: str, lang: str = "en") -> Optional[List[dict]]:
    """Every requisition row, paging until ``totalCount`` is reached.

    Returns None when the first page cannot be read.
    """
    url = search_url(host, portal, lang=lang)
    headers = {"Content-Type": "application/json", "tz": "GMT+08:00"}
    collected: List[dict] = []
    total = None
    for page in range(1, _MAX_PAGES + 1):
        body = dict(_SEARCH_BODY)
        body["pageNo"] = page
        data = api_request("POST", url, json_body=body, extra_headers=headers)
        if not isinstance(data, dict):
            return None if page == 1 else collected
        rows = data.get("requisitionList") or []
        if not isinstance(rows, list):
            return None if page == 1 else collected
        paging = data.get("pagingData") or {}
        if total is None:
            try:
                total = int(paging.get("totalCount") or 0)
            except (TypeError, ValueError):
                total = 0
        collected.extend(row for row in rows if isinstance(row, dict))
        if not rows or (total is not None and len(collected) >= total):
            break
        time.sleep(REQUEST_DELAY)
    return collected


def _unescape(value: str) -> str:
    text = unquote(value or "")
    if text.startswith("!*!"):
        text = text[3:]
    return (
        text.replace("\\:", ":")
        .replace("\\'", "'")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
        .strip()
    )


def parse_detail_html(html: str) -> dict:
    """Title, department, description and unposting date from a Taleo detail page.

    Field order is not stable across tenants, so values are zipped to the
    ``reqlistitem.*`` names embedded in the page.
    """
    if not html:
        return {}
    parts = html.split("!|!")
    try:
        start = parts.index("descRequisition") + 1
        end = parts.index("descRequisition.size")
    except ValueError:
        return {}
    values = [_unescape(part) for part in parts[start:end]]
    lists = _FIELD_LIST.findall(html)
    if not lists:
        return {}
    fields = max(lists, key=len).split("','")
    bag = {}
    for field, value in zip(fields, values):
        bag.setdefault(field, value)
    description = html_to_text(bag.get("reqlistitem.description") or "")
    return {
        "title": bag.get("reqlistitem.title") or "",
        "contest_no": bag.get("reqlistitem.contestnumber") or "",
        "organization": bag.get("reqlistitem.organization") or "",
        "job_field": bag.get("reqlistitem.jobfield") or "",
        "description": description,
        "unposting_date": bag.get("reqlistitem.unpostingdate") or "",
    }


def fetch_detail(url: str) -> Optional[dict]:
    html = api_request("GET", url, expect="text")
    if not html:
        return None
    parsed = parse_detail_html(html)
    return parsed or None
