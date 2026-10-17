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
"""

from typing import Any, Dict, List, Optional

from services import vector_store

DEFAULT_LIMIT = 10
MAX_LIMIT = 50

#: A role card shows a short list; the candidate opens more by searching.
ROLE_DEFAULT_LIMIT = 5


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


def search_postings(query: str, limit: int = DEFAULT_LIMIT) -> Dict[str, Any]:
    """The `job_role` postings nearest to `query`, best first."""
    text = (query or "").strip()
    available = vector_store.is_available() and vector_store.collection_exists(
        vector_store.JOBS_COLLECTION
    )
    hits: List = (
        vector_store.search_records(vector_store.JOBS_COLLECTION, text, limit=limit)
        if available
        else []
    )
    return {
        "query": text,
        "available": available,
        "count": len(hits),
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
