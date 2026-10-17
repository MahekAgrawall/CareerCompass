"""
Live job postings, as the API sees them.

The postings are collected, normalised and embedded by `scripts.ingest_jobs`
(see `services.job_feed`); this module is the read path: a semantic search over
the `job_role` collection with the stored payload shaped into something a client
can render.

There is deliberately no fallback source here. Role matching degrades to
keyword-only because the curated catalog exists in full outside the index, but
the index is the *only* copy of the live postings — so rather than invent a
weaker search, the response says whether the index answered (`available`) and
returns no rows when it did not. The endpoint therefore works in every
deployment, and a client can hide the section instead of surfacing an error.

Location, work arrangement and experience are *store* filters, not post-filters:
they travel to Qdrant as a payload filter, so they narrow the whole collection
and `matched` is an honest count of it. Running them in Python over the ranked
window instead would make every number on the page a statement about the fifty
postings the search happened to return.

Every response also carries `freshness` (see the function): the date the postings
were harvested, and whether that is old enough to warn about. Live postings age —
a board keeps serving a listing after it is filled — so "12 of 87 matching" is
only half a sentence without "harvested 20 days ago".
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services import vector_store

DEFAULT_LIMIT = 10
MAX_LIMIT = 50

#: A role card shows a short list; the candidate opens more by searching.
ROLE_DEFAULT_LIMIT = 5

#: How old a harvest may get before the page says so. Two weeks is longer than a
#: board's own listings usually survive, so past this the note is honest advice
#: rather than a nag. `scripts.ingest_jobs --if-stale` defaults to the same
#: number, so "too old to show without comment" and "time to refresh" agree.
STALE_AFTER_DAYS = 14

#: The experience buckets a client may ask for. Boards leave `seniority` blank
#: for almost every posting (only one of the two boards publishes it at all), so
#: a bucket also matches the title and the contract wording — which is why there
#: are three meaningful levels rather than a list of seniority labels.
EXPERIENCE_LEVELS = ("internship", "entry", "senior")

#: Bucket -> the words that put a posting in it. Matching happens in Qdrant's
#: full-text (`MatchText`) condition, so a needle is matched as a *token*: "intern"
#: no longer catches "Internal Tools Engineer", and "entry-level" catches "Entry
#: Level Analyst" — stricter and more accurate than the substring rules these
#: replaced.
_EXPERIENCE_RULES: Dict[str, Dict[str, tuple]] = {
    "internship": {
        "title": ("intern", "working student", "werkstudent", "praktik", "trainee"),
        "seniority": (),
        "employment_type": ("intern", "working student", "werkstudent", "praktik"),
    },
    "entry": {
        "title": ("junior", "entry level", "graduate"),
        "seniority": ("entry-level", "graduate"),
        "employment_type": (),
    },
    "senior": {
        "title": ("senior", "sr", "lead", "principal", "staff", "head of", "director"),
        "seniority": ("senior", "director", "executive"),
        "employment_type": (),
    },
}

#: The payload fields the filters above read, and the index each needs. The
#: ingest applies this (`scripts.ingest_jobs`); the embedded store ignores
#: payload indexes, but a server-backed one needs the text indexes before it will
#: run a `MatchText` condition at all.
FILTER_INDEXES = {
    "location": "text",
    "title": "text",
    "seniority": "text",
    "employment_type": "text",
    "remote": "bool",
}


def _result(score: float, payload: Dict[str, Any]) -> Dict[str, Any]:
    """One stored posting, shaped for the response.

    Fields are picked one by one rather than forwarded wholesale: the stored
    payload stays free to grow, and a client cannot come to depend on internals
    that happen to be in the vector store.
    """
    return {
        "id": str(payload.get("id") or ""),
        "title": str(payload.get("title") or ""),
        "company": str(payload.get("company") or ""),
        "location": str(payload.get("location") or ""),
        "remote": bool(payload.get("remote")),
        "employment_type": str(payload.get("employment_type") or ""),
        "seniority": [str(item) for item in payload.get("seniority") or []],
        "categories": [str(item) for item in payload.get("categories") or []],
        "salary_text": str(payload.get("salary_text") or ""),
        "published": str(payload.get("published") or ""),
        "url": str(payload.get("url") or ""),
        "source": str(payload.get("source") or ""),
        "excerpt": str(payload.get("excerpt") or ""),
        "similarity": round(float(score), 4),
    }


def ranking_text(
    query: str = "",
    location: str = "",
    remote: Optional[bool] = None,
    experience: str = "",
) -> str:
    """The text the ranking runs on: the caller's own words, or the filters.

    A search box is not the only way in — a candidate may want "every senior
    remote posting" and type nothing — so the filter terms stand in for the
    query when there are none. That keeps one ranking path, and `search_postings`
    echoes whichever text it used, so the response never claims a ranking the
    caller did not ask for.
    """
    parts = [str(query or "").strip(), str(location or "").strip()]
    if remote is not None:
        parts.append("remote" if remote else "on-site")
    if experience:
        parts.append(str(experience).strip())
    return " ".join(part for part in parts if part)


def posting_filter(
    location: str = "",
    remote: Optional[bool] = None,
    experience: str = "",
):
    """The Qdrant filter behind the Jobs page, or `None` when nothing narrows.

    Each dimension is a nested `should`, so the conditions *within* one dimension
    are alternatives ("Berlin" or a remote flag) while the dimensions themselves
    are all required. An unrecognised experience bucket is ignored here rather
    than raising: the endpoint types it as a literal, so a client cannot get this
    far with one, and a store filter is the wrong place to answer 500s.
    """
    from qdrant_client import models

    must: List[Any] = []
    if remote is not None:
        must.append(
            models.FieldCondition(key="remote", match=models.MatchValue(value=bool(remote)))
        )

    place = str(location or "").strip()
    if place:
        alternatives = [
            models.FieldCondition(key="location", match=models.MatchText(text=place))
        ]
        # "Remote" is a work arrangement, not a place name: the boards use it for
        # the flag and for the literal string both, so either one counts.
        if place.lower().startswith("remote"):
            alternatives.append(
                models.FieldCondition(key="remote", match=models.MatchValue(value=True))
            )
        must.append(models.Filter(should=alternatives))

    rules = _EXPERIENCE_RULES.get(str(experience or "").strip().lower())
    if rules:
        must.append(
            models.Filter(
                should=[
                    models.FieldCondition(key=field, match=models.MatchText(text=word))
                    for field in ("title", "seniority", "employment_type")
                    for word in rules[field]
                ]
            )
        )

    return models.Filter(must=must) if must else None


def age_days(harvested_at: str) -> Optional[int]:
    """Whole UTC days since `harvested_at`, or None when it is not a timestamp.

    Floors rather than rounds, so "13 days and 23 hours" still reads as 13 — the
    page never claims more age than the record supports.
    """
    if not harvested_at:
        return None
    try:
        harvested = datetime.fromisoformat(str(harvested_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if harvested.tzinfo is None:
        harvested = harvested.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - harvested).days)


def freshness(meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """When the live postings were harvested, and whether that is getting old.

    Read from the sidecar `scripts.ingest_jobs` writes beside the collection
    (`vector_store.record_meta`), not derived from the postings: the boards'
    publication dates say when a job was posted, never when we last looked. Every
    date is UTC ISO 8601, and an empty string means "not recorded" — the honest
    answer on a `QDRANT_URL` deployment, whose sidecar lives next to the ingest.

    `age_days` is whole days since the harvest (None when unknown) and `stale`
    is True once that reaches `STALE_AFTER_DAYS`; a client is given both, plus
    the threshold, so it can word the warning without hard-coding the number.
    """
    meta = vector_store.recorded_meta(vector_store.JOBS_COLLECTION) if meta is None else meta
    harvested_at = str(meta.get("harvested_at") or "")
    age = age_days(harvested_at)
    return {
        "harvested_at": harvested_at,
        "ingested_at": str(meta.get("ingested_at") or ""),
        "age_days": age,
        "stale": age is not None and age >= STALE_AFTER_DAYS,
        "stale_after_days": STALE_AFTER_DAYS,
    }


def search_postings(
    query: str = "",
    limit: int = DEFAULT_LIMIT,
    location: str = "",
    remote: Optional[bool] = None,
    experience: str = "",
) -> Dict[str, Any]:
    """The `job_role` postings nearest to the search text, narrowed by filters.

    `matched` counts the postings the filters leave *in the whole collection*, as
    opposed to `count`, which is how many of them came back in this page. Both
    are reported so a client can show "12 of 87 matching, 951 indexed" without
    implying it inspected more than it did.
    """
    text = ranking_text(query, location, remote, experience)
    query_filter = posting_filter(location, remote, experience)
    available = vector_store.is_available() and vector_store.collection_exists(
        vector_store.JOBS_COLLECTION
    )
    hits: List = (
        vector_store.search_records(
            vector_store.JOBS_COLLECTION, text, limit=limit, query_filter=query_filter
        )
        if available
        else []
    )
    return {
        "query": text,
        "available": available,
        "count": len(hits),
        "matched": (
            vector_store.count_points(vector_store.JOBS_COLLECTION, query_filter)
            if available
            else 0
        ),
        "indexed": (
            vector_store.count_points(vector_store.JOBS_COLLECTION) if available else 0
        ),
        "freshness": freshness(),
        "results": [_result(score, payload) for score, payload in hits],
    }


def role_query(role: Dict[str, Any], profile: Optional[Dict[str, Any]] = None) -> str:
    """The text a role's postings are searched with.

    The role's own index document says *what* the posting should be; the
    candidate's questionnaire answers say what should come first for them. Both
    go into one query, so an empty profile degrades to a plain role search rather
    than failing.
    """
    parts = [vector_store.role_document(role)]
    personal = vector_store.profile_query(profile or {})
    if personal:
        parts.append(personal)
    return "\n\n".join(part for part in parts if part.strip())


def search_for_role(
    role: Dict[str, Any],
    profile: Optional[Dict[str, Any]] = None,
    limit: int = ROLE_DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """The `job_role` postings nearest to one catalogued role, best first.

    Same honesty contract as `search_postings`: no index means no rows and
    `available: false`, never an invented fallback.
    """
    available = vector_store.is_available() and vector_store.collection_exists(
        vector_store.JOBS_COLLECTION
    )
    hits: List = (
        vector_store.search_records(
            vector_store.JOBS_COLLECTION, role_query(role, profile), limit=limit
        )
        if available
        else []
    )
    return {
        "role_id": str(role.get("id") or ""),
        "role_title": str(role.get("title") or ""),
        "available": available,
        "count": len(hits),
        "results": [_result(score, payload) for score, payload in hits],
    }
