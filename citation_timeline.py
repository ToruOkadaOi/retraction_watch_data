"""Fetch and date direct citations without importing them into the graph."""

import calendar
import json
import re
import time
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import date, datetime, timezone
from functools import lru_cache
from urllib.parse import quote

import httpx

BASE_URL = "https://api.opencitations.net"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
CACHE_SECONDS = 900
DOI_PATTERN = r"10\.\d{4,9}/\S+"


class CitationSourceError(Exception):
    """The provider did not return a usable citation response."""


def original_identifier(doi, pmid):
    doi = re.sub(
        r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)",
        "",
        (doi or "").strip(),
        flags=re.IGNORECASE,
    )
    if len(doi) <= 512 and re.fullmatch(DOI_PATTERN, doi):
        return f"doi:{doi.lower()}"
    pmid = (pmid or "").strip()
    if re.fullmatch(r"[0-9]{1,18}", pmid) and int(pmid):
        return f"pmid:{int(pmid)}"
    return None


def provider_rows(path):
    try:
        with httpx.stream(
            "GET", BASE_URL + path, timeout=8, headers={"Accept": "application/json"}
        ) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise CitationSourceError(
                        "Citation source response exceeded the size limit"
                    )
        rows = json.loads(body)
    except (httpx.HTTPError, ValueError) as exc:
        raise CitationSourceError("OpenCitations did not return usable data") from exc
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise CitationSourceError("OpenCitations returned an unexpected response")
    return rows


def date_bounds(value):
    """Represent partial dates as intervals instead of filling in missing days."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            day = date.fromisoformat(value)
            return day, day
        if re.fullmatch(r"\d{4}-\d{2}", value):
            year, month = map(int, value.split("-"))
            return date(year, month, 1), date(
                year, month, calendar.monthrange(year, month)[1]
            )
        if re.fullmatch(r"\d{4}", value):
            return date(int(value), 1, 1), date(int(value), 12, 31)
        raw_date = value.split()[0] if value else ""
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", raw_date):
            month, day, year = map(int, raw_date.split("/"))
            day = date(year, month, day)
            return day, day
    except ValueError:
        return None
    return None


def identifiers(value):
    return value.split() if isinstance(value, str) else []


def citing_work(row):
    pids = identifiers(row.get("citing"))
    omid = next((x for x in pids if re.fullmatch(r"omid:br/\d+", x)), None)
    doi = next(
        (x for x in pids if x.startswith("doi:") and re.fullmatch(DOI_PATTERN, x[4:])),
        None,
    )
    pmid = next((x for x in pids if re.fullmatch(r"pmid:[1-9][0-9]*", x)), None)
    oci = row.get("oci", "")
    if not isinstance(oci, str) or not re.fullmatch(r"\d+-\d+", oci):
        raise CitationSourceError(
            "OpenCitations returned a citation without a valid identifier"
        )
    publication_date = row.get("creation", "")
    bounds = date_bounds(publication_date)
    return {
        "key": omid or (doi and doi.lower()) or pmid or oci,
        "metadata_id": omid or doi,
        "doi": doi[4:] if doi else None,
        "pmid": pmid[5:] if pmid else None,
        "oci": oci,
        "publication_date": publication_date.strip() if bounds else None,
    }


@lru_cache(maxsize=16)
def indexed_citations(identifier, cache_window):
    rows = provider_rows("/index/v2/citations/" + quote(identifier, safe=":/"))
    by_work = {}
    for row in rows:
        work = citing_work(row)
        previous = by_work.get(work["key"])
        if previous is None or (
            not previous["publication_date"] and work["publication_date"]
        ):
            by_work[work["key"]] = work
    return tuple(by_work.values()), datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=64)
def work_titles(ids, cache_window):
    rows = provider_rows("/meta/v1/metadata/" + quote("__".join(ids), safe=":/"))
    return {
        pid: row["title"].strip()
        for row in rows
        if isinstance(row.get("title"), str) and row["title"].strip()
        for pid in identifiers(row.get("id"))
    }


def timeline(notice_result, identifier, period, skip, limit):
    window = int(time.monotonic()) // CACHE_SECONDS
    indexed, retrieved_at = indexed_citations(identifier, window)
    notices = []
    for record in notice_result["notices"]:
        bounds = date_bounds(record.get("retraction_date"))
        notice_date = (
            bounds[0].isoformat() if bounds and bounds[0] == bounds[1] else None
        )
        notices.append({**record, "timeline_date": notice_date})
    notices.sort(
        key=lambda record: (
            record["timeline_date"] or "9999-99-99",
            record["record_id"],
        )
    )
    dates = sorted(
        {
            date.fromisoformat(row["timeline_date"])
            for row in notices
            if row["timeline_date"]
        }
    )

    groups = []
    if dates and not notice_result["has_more"]:
        for i in range(len(dates) + 1):
            groups.append(
                {
                    "id": f"interval-{i}",
                    "after": dates[i - 1] if i else None,
                    "before": dates[i] if i < len(dates) else None,
                }
            )
    groups.extend(
        [{"id": "notice-date"}, {"id": "uncertain"}]
        if groups
        else [{"id": "uncertain"}]
    )

    def assign_period(bounds):
        if not bounds or not dates or notice_result["has_more"]:
            return "uncertain"
        low, high = bounds
        left = bisect_left(dates, low)
        right = bisect_right(dates, high)
        if left == right:
            return f"interval-{left}"
        return "notice-date" if low == high else "uncertain"

    works = [
        {**work, "period": assign_period(date_bounds(work["publication_date"]))}
        for work in indexed
    ]
    works.sort(
        key=lambda work: (
            work["publication_date"] is None,
            work["publication_date"] or "",
            work["key"],
        )
    )
    counts = Counter(work["period"] for work in works)
    filtered = (
        works
        if period == "all"
        else [work for work in works if work["period"] == period]
    )
    page = filtered[skip : skip + limit]
    ids = tuple(sorted({work["metadata_id"] for work in page if work["metadata_id"]}))
    titles = {}
    if ids:
        try:
            titles = work_titles(ids, window)
        except CitationSourceError:
            pass  # A missing title does not invalidate a citation or its date.

    return {
        "identifier": identifier,
        "citation_source": "OpenCitations",
        "citation_retrieved_at": retrieved_at,
        "source_sha256": notice_result["source_sha256"],
        "snapshot_generation": notice_result["snapshot_generation"],
        "notices": notices,
        "notices_truncated": notice_result["has_more"],
        "periods": [{**group, "count": counts[group["id"]]} for group in groups],
        "indexed_count": len(works),
        "filtered_count": len(filtered),
        "skip": skip,
        "limit": limit,
        "citations": [
            {
                **{
                    k: work[k]
                    for k in ("doi", "pmid", "oci", "publication_date", "period")
                },
                "title": titles.get(work["metadata_id"]),
            }
            for work in page
        ],
    }
