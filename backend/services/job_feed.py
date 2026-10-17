"""
Live job postings, collected from public job-board APIs.

The curated role catalog (`data/roles.json`) answers *what is this career like?*
This module answers *what is actually open right now?* — it pulls from free,
no-key, public JSON APIs, normalises every board's shape into one posting record,
and strips the HTML so the text can be embedded and searched.

| Board | Endpoint | Paging | Terms |
|---|---|---|---|
| Himalayas | `himalayas.app/jobs/api` | `?limit=` (max 20) + `?offset=` | public feed |
| Arbeitnow | `arbeitnow.com/api/job-board-api` | `?page=` (300/page) | asks callers not to abuse it and to link back |

Both asks are respected: a descriptive `User-Agent`, a short pause between pages,
a hard cap on pages per source, and every posting keeps its board name and its own
URL so the original listing stays one click away.

What is collected is written to an artifact that records **when it was pulled**
(`save`/`load_artifact`), because postings age: a board goes on serving a listing
after the job is filled, and nothing in the posting itself says when we looked.
That stamp travels with the data into the index, so the API can tell a candidate
how old the feed is instead of implying it is live.

Network access is confined to `_get_json`, so the whole module can be tested
offline against captured fixtures. Normalisation, de-duplication and document
building are pure functions.
"""

import html
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx

from app_logging import get_logger

log = get_logger("careercompass.jobs")

SOURCE_HIMALAYAS = "himalayas"
SOURCE_ARBEITNOW = "arbeitnow"
SOURCES: Sequence[str] = (SOURCE_HIMALAYAS, SOURCE_ARBEITNOW)

HIMALAYAS_URL = "https://himalayas.app/jobs/api"
ARBEITNOW_URL = "https://arbeitnow.com/api/job-board-api"

# Request manners, and the per-source page ceiling that keeps us a polite guest.
USER_AGENT = "CareerCompass/1.0 (educational career-guidance project)"
REQUEST_TIMEOUT = 25.0
PAUSE_SECONDS = 0.4
PAGE_SIZE = {SOURCE_HIMALAYAS: 20, SOURCE_ARBEITNOW: 300}
MAX_PAGES = {SOURCE_HIMALAYAS: 5, SOURCE_ARBEITNOW: 4}

# How much listing text is kept in the payload, and how much is embedded.
PAYLOAD_EXCERPT = 320
DOCUMENT_EXCERPT = 700

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_KEY_RE = re.compile(r"[^a-z0-9]+")


# ── HTTP ──────────────────────────────────────────────────────────────────────
def _pause(seconds: float = PAUSE_SECONDS) -> None:
    """A deliberate pause between page requests (patched out in tests)."""
    if seconds > 0:
        time.sleep(seconds)


def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fetches one JSON document. The only function here that touches the network."""
    response = httpx.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    response.raise_for_status()
    return response.json()


# ── Field helpers ─────────────────────────────────────────────────────────────
def _text(value: Any) -> str:
    """Plain text from a possibly-HTML, possibly-escaped value."""
    if value is None:
        return ""
    unescaped = html.unescape(str(value))
    return _SPACE_RE.sub(" ", _TAG_RE.sub(" ", unescaped)).strip()


def _as_int(value: Any) -> Optional[int]:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    items: List[str] = []
    for entry in value:
        text = _text(entry)
        if text and text not in items:
            items.append(text)
    return items


def _iso_date(epoch: Any) -> str:
    try:
        moment = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return ""
    return moment.strftime("%Y-%m-%d")


def _dedupe_key(posting: Dict[str, Any]) -> str:
    """Board-independent key: the same opening is the same opening."""
    title = _KEY_RE.sub(" ", str(posting.get("title") or "").lower()).strip()
    company = _KEY_RE.sub(" ", str(posting.get("company") or "").lower()).strip()
    return f"{title}|{company}"


# ── Normalisation ─────────────────────────────────────────────────────────────
def _base_posting(source: str) -> Dict[str, Any]:
    return {
        "id": "",
        "source": source,
        "title": "",
        "company": "",
        "location": "",
        "remote": False,
        "employment_type": "",
        "seniority": [],
        "categories": [],
        "tags": [],
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "",
        "salary_period": "",
        "published": "",
        "url": "",
        "description": "",
    }


def normalise_himalayas(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One Himalayas posting -> the shared posting shape (None when unusable)."""
    title = _text(raw.get("title"))
    url = _text(raw.get("applicationLink")) or _text(raw.get("guid"))
    if not (title and url):
        return None
    posting = _base_posting(SOURCE_HIMALAYAS)
    restrictions = _string_list(raw.get("locationRestrictions"))
    posting.update(
        {
            "id": f"{SOURCE_HIMALAYAS}:{_text(raw.get('guid')) or url}",
            "title": title,
            "company": _text(raw.get("companyName")),
            "location": ", ".join(restrictions) or "Remote",
            "remote": True,  # Himalayas only lists remote-friendly roles
            "employment_type": _text(raw.get("employmentType")),
            "seniority": _string_list(raw.get("seniority")),
            "categories": _string_list(raw.get("parentCategories")) + _string_list(raw.get("categories")),
            "salary_min": _as_int(raw.get("minSalary")),
            "salary_max": _as_int(raw.get("maxSalary")),
            "salary_currency": _text(raw.get("currency")),
            "salary_period": _text(raw.get("salaryPeriod")),
            "published": _iso_date(raw.get("pubDate")),
            "url": url,
            "description": _text(raw.get("description")),
        }
    )
    return posting


def normalise_arbeitnow(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One Arbeitnow posting -> the shared posting shape (None when unusable)."""
    title = _text(raw.get("title"))
    url = _text(raw.get("url"))
    if not (title and url):
        return None
    location = _text(raw.get("location"))
    posting = _base_posting(SOURCE_ARBEITNOW)
    posting.update(
        {
            "id": f"{SOURCE_ARBEITNOW}:{_text(raw.get('slug')) or url}",
            "title": title,
            "company": _text(raw.get("company_name")),
            "location": location or ("Remote" if raw.get("remote") else ""),
            "remote": bool(raw.get("remote")),
            "employment_type": ", ".join(_string_list(raw.get("job_types"))),
            "categories": _string_list(raw.get("tags")),
            "tags": _string_list(raw.get("tags")),
            "published": _iso_date(raw.get("created_at")),
            "url": url,
            "description": _text(raw.get("description")),
        }
    )
    return posting


NORMALISERS = {
    SOURCE_HIMALAYAS: normalise_himalayas,
    SOURCE_ARBEITNOW: normalise_arbeitnow,
}


# ── Collection ────────────────────────────────────────────────────────────────
def dedupe(postings: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keeps the first posting per (title, company).

    The same opening is routinely advertised on several boards, and for a text
    corpus a duplicate title adds nothing but noise. Titles are compared
    case-insensitively and ignoring punctuation, so "Senior Backend Engineer
    (m/f/d)" and "senior backend engineer" collapse together.
    """
    seen = set()
    unique: List[Dict[str, Any]] = []
    for posting in postings:
        key = _dedupe_key(posting)
        if key in seen:
            continue
        seen.add(key)
        unique.append(posting)
    return unique


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def salary_text(posting: Dict[str, Any]) -> str:
    """Human-readable salary, e.g. 'USD 90000-120000 / year'. '' when unknown."""
    low = posting.get("salary_min")
    high = posting.get("salary_max")
    if low is None and high is None:
        return ""
    currency = posting.get("salary_currency") or ""
    period = posting.get("salary_period") or ""
    if low and high:
        amount = f"{low}-{high}" if low != high else f"{low}"
    else:
        amount = f"{low or high}"
    parts = [part for part in (currency, amount, f"/ {period}" if period else "") if part]
    return " ".join(parts).strip()


def posting_document(posting: Dict[str, Any]) -> str:
    """The text embedded for a posting — what a candidate would search on."""
    categories = list(posting.get("categories") or []) + list(posting.get("tags") or [])
    parts = [
        str(posting.get("title") or ""),
        f"Company: {posting['company']}" if posting.get("company") else "",
        f"Location: {posting['location']}" if posting.get("location") else "",
        "Remote" if posting.get("remote") else "",
        f"Employment: {posting['employment_type']}" if posting.get("employment_type") else "",
        f"Seniority: {', '.join(posting.get('seniority') or [])}" if posting.get("seniority") else "",
        f"Categories: {', '.join(dict.fromkeys(categories))}" if categories else "",
        f"Salary: {salary_text(posting)}" if salary_text(posting) else "",
        _truncate(str(posting.get("description") or ""), DOCUMENT_EXCERPT),
    ]
    return "\n".join(part for part in parts if part.strip())


def posting_payload(posting: Dict[str, Any]) -> Dict[str, Any]:
    """The stored, displayable record: everything but the long description."""
    payload = {key: value for key, value in posting.items() if key != "description"}
    payload["excerpt"] = _truncate(str(posting.get("description") or ""), PAYLOAD_EXCERPT)
    payload["salary_text"] = salary_text(posting)
    return payload


def row_for(posting: Dict[str, Any]) -> Dict[str, Any]:
    """The `(id, document, payload)` triple `vector_store.upsert_records` wants."""
    return {
        "record_id": str(posting.get("id") or posting.get("url") or ""),
        "document": posting_document(posting),
        "payload": posting_payload(posting),
    }


# ── Fetching ──────────────────────────────────────────────────────────────────
def fetch_source(source: str, limit: int) -> List[Dict[str, Any]]:
    """Postings from one board, newest-first as the board returns them."""
    if source not in NORMALISERS:
        raise ValueError(f"Unknown job source {source!r}; expected one of {list(NORMALISERS)}")
    normalise = NORMALISERS[source]
    page_size = PAGE_SIZE[source]
    max_pages = MAX_PAGES[source]
    url = HIMALAYAS_URL if source == SOURCE_HIMALAYAS else ARBEITNOW_URL

    collected: List[Dict[str, Any]] = []
    for page in range(max_pages):
        if len(collected) >= limit:
            break
        if source == SOURCE_HIMALAYAS:
            payload = _get_json(url, {"limit": page_size, "offset": page * page_size})
            raw_items = payload.get("jobs") or []
        else:
            payload = _get_json(url, {"page": page + 1})
            raw_items = payload.get("data") or []
        if not raw_items:
            break
        for raw in raw_items:
            posting = normalise(raw)
            if posting:
                collected.append(posting)
        if len(raw_items) < page_size:
            break
        _pause()
    log.info("Fetched %d postings from %s", len(collected), source)
    return collected[:limit]


def collect(
    limit: int = 1000,
    sources: Sequence[str] = SOURCES,
    on_progress: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Postings from every requested board, de-duplicated, capped at `limit`."""
    collected: List[Dict[str, Any]] = []
    for source in sources:
        if len(collected) >= limit:
            break
        remaining = limit - len(collected)
        try:
            fetched = fetch_source(source, remaining)
        except Exception as exc:  # a board being down must not sink the rest
            log.warning("Skipping %s (%s)", source, exc)
            if on_progress:
                on_progress(source, 0, str(exc))
            continue
        collected.extend(fetched)
        if on_progress:
            on_progress(source, len(fetched), "")
    return dedupe(collected)[:limit]


def rows(postings: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every posting as an upsert row, ids included."""
    return [row_for(posting) for posting in postings if posting.get("id")]


# ── Artifact ──────────────────────────────────────────────────────────────────
def harvest_stamp() -> str:
    """Now, in the form an artifact records it: UTC, ISO 8601, second precision.

    Seconds rather than microseconds because this is a date a person reads, not
    an event to order: `2026-10-18T09:14:02+00:00`.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(
    postings: List[Dict[str, Any]], path: str, harvested_at: str = ""
) -> str:
    """Writes the collected postings *and when they were pulled*.

    The timestamp is the artifact's own provenance. A board keeps serving a
    listing after the job is filled, so postings age silently — the publication
    dates say when a job was posted, never when we looked at it — and an index
    built from this file inherits whatever date is written here. Passing one in
    keeps `--from-file` honest, because a re-ingest of an old artifact must not
    claim today's date.
    """
    artifact = {
        "harvested_at": harvested_at or harvest_stamp(),
        "postings": list(postings),
    }
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=1)
    return path


def load_artifact(path: str) -> Dict[str, Any]:
    """The artifact as saved: `{"harvested_at": ..., "postings": [...]}`.

    A bare JSON list is accepted as an artifact written before the harvest time
    was recorded: it loads with an empty stamp rather than failing, so a file
    collected by an older version still re-ingests.
    """
    with open(path, encoding="utf-8") as handle:
        artifact = json.load(handle)
    if isinstance(artifact, list):
        return {"harvested_at": "", "postings": artifact}
    if not isinstance(artifact, dict):
        return {"harvested_at": "", "postings": []}
    postings = artifact.get("postings")
    return {
        "harvested_at": str(artifact.get("harvested_at") or ""),
        "postings": list(postings) if isinstance(postings, list) else [],
    }


def load(path: str) -> List[Dict[str, Any]]:
    """Reads a previously collected artifact (see `save`)."""
    return load_artifact(path)["postings"]
