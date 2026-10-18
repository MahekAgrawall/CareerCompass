"""
Live job postings, as the API sees them.

The postings are collected, normalised and embedded by `scripts.ingest_jobs`
(see `services.job_feed`); this module is the read path: a search over the
`job_role` collection with the stored payload shaped into something a client can
render. The store ranks by meaning, and `_rank` lifts a posting whose *title*
carries the query above one the store merely placed near it — a search box has to
answer "python" with the job called Python.

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

The places the search box suggests come from the collection too, and each count is
asked of that same filter (`locations`), because the boards publish free-text
locations — "Berlin" and "Berlin, Germany" are two strings for one city — and a
list built from the postings a previous search returned offered whatever ran last.

Every response also carries `freshness` (see the function): the date the postings
were harvested, and whether that is old enough to warn about. Live postings age —
a board keeps serving a listing after it is filled — so "12 of 87 matching" is
only half a sentence without "harvested 20 days ago".
"""

import re
from collections import Counter
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

#: How many places the Jobs page's location field is offered (see `locations`).
#: The boards' postings cluster into a handful of cities and countries, so this
#: covers browsing by place without becoming a dump of every village they publish.
LOCATION_OPTION_LIMIT = 25

#: Extra candidates counted before the list is cut to `LOCATION_OPTION_LIMIT`: a
#: candidate whose wording does not survive the store's tokenizer (a hyphenated
#: district, say) counts zero and is dropped, so the spare ones keep the list full
#: without the caller ever being offered a dead end.
LOCATION_OPTION_SPARE = 10

#: How many postings the vocabulary is read from. Bounded so a very large index
#: still answers in one request; the field stays free text, so a place the sample
#: happens not to mention can still be typed.
LOCATION_SCAN_LIMIT = 5000

#: Segments the boards put in `location` that name no place at all.
_NOT_A_PLACE = {"n/a", "na", "none", "unknown", "tbd", "various", "not specified"}

#: One entry: the place vocabulary, keyed by the index state it was read from.
#: Thirty filtered counts are not free, and the vocabulary only changes when the
#: postings do, so the last answer is kept rather than recomputed per page view.
_LOCATION_CACHE: Dict[str, Any] = {}

#: What a query word appearing in a posting's *title* is worth: a tier. The store
#: ranks by meaning alone, which is not enough for a search box, and not something
#: a fixed weight can patch — with the offline embedder a description that *repeats*
#: the word scores 0.55 against 0.21 for the posting whose title says it, while a
#: hosted embedder's cosines sit in the 0.7s with no such gap. Counting matched
#: words instead needs no tuning: postings that match on more of the query come
#: first, and the store's meaning ranks within a tier (see `_rank`).
RANK_WINDOW = 4

#: And a ceiling on that, so a 50-row page cannot ask the store for 500 rows.
MAX_RANK_WINDOW = 200

#: Words a title should not be judged on: they are in half of them already.
_STOP_WORDS = {"a", "an", "and", "at", "for", "in", "of", "on", "or", "the", "to", "with"}


def _result(
    score: float, payload: Dict[str, Any], matched: Optional[List[str]] = None
) -> Dict[str, Any]:
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
        # The cosine similarity to the search text: how near the posting is in
        # meaning. Ordering also weighs a title match (see `_rank`), which is why
        # the words the title carried are reported beside it rather than folded
        # into this number.
        "similarity": round(float(score), 4),
        # The query words this posting's title contains, in the order they were
        # typed. Empty for a read that ranks by meaning alone (`/jobs/for-role`,
        # and any query none of the titles carries).
        "matched_terms": list(matched or []),
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


def _is_place(value: str) -> bool:
    """Whether one comma-separated location segment is worth offering.

    The boards mix postcodes, numbered districts and street addresses into the
    same field ("9th arrondissement of Paris, 75009, Paris"), and a picker is the
    wrong place to show them: a segment with a digit in it is a number or a
    numbered district, never a place someone looks for by name.

    "Remote Switzerland" is dropped for a different reason: `posting_filter`
    widens any "remote…" place to the boards' own remote flag, so offering it
    would advertise a count of every remote posting rather than of Swiss ones.
    "Remote" on its own is offered, and the work-arrangement field is the honest
    way to ask for the rest.
    """
    if not 2 < len(value) <= 40:
        return False
    if any(character.isdigit() for character in value):
        return False
    key = value.casefold()
    if key.startswith("remote") and key != "remote":
        return False
    return key not in _NOT_A_PLACE


def _location_candidates(postings: List[str]) -> List[str]:
    """The places those postings name, most mentioned first.

    Cut from the boards' own wording rather than a list of our own: they have no
    location vocabulary, so one city can arrive as "Berlin", "Berlin, Germany" or
    "Amsterdam, Noord-Holland, Nederland". Segments are counted once per posting,
    and casing follows the most common spelling, so the list reads the way the
    boards wrote it instead of the way a normalisation step rewrote it.
    """
    spellings: Dict[str, Counter] = {}
    for location in postings:
        counted = set()
        for segment in re.split(r"[;,/|]", location):
            value = " ".join(segment.split())
            if not _is_place(value):
                continue
            key = value.casefold()
            if key in counted:
                continue
            counted.add(key)
            spellings.setdefault(key, Counter())[value] += 1

    ranked = []
    for spellings_for_place in spellings.values():
        display = sorted(spellings_for_place.items(), key=lambda item: (-item[1], item[0]))[0][0]
        ranked.append((-sum(spellings_for_place.values()), display.casefold(), display))
    return [display for _, _, display in sorted(ranked)]


def _location_cache_key() -> str:
    """What a vocabulary depends on: the store, the index, and its recorded state."""
    meta = vector_store.recorded_meta(vector_store.JOBS_COLLECTION)
    return "|".join(
        (
            vector_store.location(),
            str(meta.get("harvested_at") or ""),
            str(meta.get("ingested_at") or ""),
            str(vector_store.count_points(vector_store.JOBS_COLLECTION)),
        )
    )


def locations(limit: int = LOCATION_OPTION_LIMIT) -> Dict[str, Any]:
    """The places the live postings actually name, commonest first, with counts.

    The location field is free text over the boards' wording, which is not a
    vocabulary — and the page used to fill its suggestions from the fifty postings
    a previous search happened to return, so it offered whatever ran last rather
    than what exists. These options come from the collection itself.

    Every count is *asked of the store filter a search would apply*, never guessed
    from the text: the number beside "Germany" is the number of postings clicking
    it will return, which is the `matched` that search then reports. A candidate
    the filter cannot match — a hyphenated district the tokenizer splits, say —
    counts zero and is dropped rather than offered as a dead end.

    Without an index this answers `available: false` and no options, like every
    other read here. Reads up to `LOCATION_SCAN_LIMIT` postings, and keeps the
    answer until the index's recorded state changes.
    """
    if not (
        vector_store.is_available()
        and vector_store.collection_exists(vector_store.JOBS_COLLECTION)
    ):
        return {"available": False, "locations": []}

    key = _location_cache_key()
    cached = _LOCATION_CACHE.get(key)
    if cached is not None:
        return cached

    named = vector_store.payload_values(
        vector_store.JOBS_COLLECTION, "location", LOCATION_SCAN_LIMIT
    )
    candidates = _location_candidates(named)[: limit + LOCATION_OPTION_SPARE]

    options = []
    for value in candidates:
        count = vector_store.count_points(
            vector_store.JOBS_COLLECTION, posting_filter(location=value)
        )
        if count:
            options.append({"value": value, "count": count})

    options.sort(key=lambda option: (-option["count"], option["value"].casefold()))
    answer = {"available": True, "locations": options[:limit]}
    _LOCATION_CACHE.clear()
    _LOCATION_CACHE[key] = answer
    return answer


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


def _words(text: str) -> set:
    """The token set of a piece of posting text.

    Split the way the store splits text: on anything that is not a letter, digit or
    one of the characters that *are* part of a language's name ("c++", "c#", ".net",
    "node.js"). Tokens, never substrings, so "intern" does not match "Internal".
    """
    return set(re.split(r"[^0-9a-z+#.]+", str(text).casefold()))


def query_terms(query: str) -> List[str]:
    """The words a posting is judged on, in the order they were typed.

    The two-letter fillers go: a title containing "of" says nothing about the
    search, and they are in half of the titles already.
    """
    terms: List[str] = []
    for word in re.split(r"[^0-9a-z+#.]+", str(query).casefold()):
        if len(word) < 2 or word in _STOP_WORDS:
            continue
        if word not in terms:
            terms.append(word)
    return terms


def title_matches(query: str, title: str) -> List[str]:
    """Which query words that title contains — as tokens, never substrings."""
    words = _words(title)
    return [term for term in query_terms(query) if term in words]


def posting_text(payload: Dict[str, Any]) -> str:
    """Everything a posting says about itself, as text to look query words up in.

    Title, company, categories and the excerpt of the description — the parts a
    search box can be judged against. The excerpt is whatever the ingest stored, so
    a description long enough to be cut is only ever matched on what was kept.
    """
    parts = [str(payload.get("title") or ""), str(payload.get("company") or "")]
    parts.extend(str(item) for item in payload.get("categories") or [])
    parts.append(str(payload.get("excerpt") or ""))
    return " ".join(parts)


def _rank(hits: List, query: str, limit: int) -> List:
    """The store's hits, resorted so a posting that says your words comes first.

    Three keys, in this order: how many of the query's words the posting's *title*
    carries, how many it carries *anywhere* in its text, and the store's own cosine.
    A single blended score was tried first and thrown away — no fixed weight suits
    both the offline embedder, whose term frequency swamps everything, and a hosted
    one whose cosines barely move. Counting words needs no weight, and the live
    index needs it: for "python" it puts a German facilities-maintenance listing
    second, in front of postings that actually name the language.

    Every tier is a no-op on a query none of the postings carry: they all land in
    one tier and the stable sort returns the index's own order untouched.

    Returned as `(matched words, cosine, payload)`, wider than the page because the
    window is what lets a posting climb at all.
    """
    terms = query_terms(query)
    scored = []
    for score, payload in hits:
        mentioned = _words(posting_text(payload))
        matched = [term for term in terms if term in _words(payload.get("title") or "")]
        scored.append(
            (
                -len(matched),
                -sum(1 for term in terms if term in mentioned),
                -float(score),
                matched,
                payload,
            )
        )
    scored.sort(key=lambda row: row[:3])
    return [(matched, -cosine, payload) for _, _, cosine, matched, payload in scored[:limit]]


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

    The store is asked for a wider window than the page and `_rank` cuts it, so a
    posting whose title carries the query can be lifted over one the vector store
    merely placed nearer — the difference between a search box and a similarity
    list.
    """
    text = ranking_text(query, location, remote, experience)
    available = vector_store.is_available() and vector_store.collection_exists(
        vector_store.JOBS_COLLECTION
    )
    # Built only when there is a store to filter. `posting_filter` needs the
    # qdrant-client models, and `is_available()` only proves an index *directory*
    # exists, so a deployment with the data but without the client used to raise
    # here — a 500 where the module promises `available: false` and no rows, the
    # way `search_for_role` answers. The filters have nothing to narrow without
    # an index anyway.
    query_filter = posting_filter(location, remote, experience) if available else None
    hits: List = (
        vector_store.search_records(
            vector_store.JOBS_COLLECTION,
            text,
            limit=min(limit * RANK_WINDOW, MAX_RANK_WINDOW),
            query_filter=query_filter,
        )
        if available
        else []
    )
    ranked = _rank(hits, text, limit)
    return {
        "query": text,
        "available": available,
        "count": len(ranked),
        "matched": (
            vector_store.count_points(vector_store.JOBS_COLLECTION, query_filter)
            if available
            else 0
        ),
        "indexed": (
            vector_store.count_points(vector_store.JOBS_COLLECTION) if available else 0
        ),
        "freshness": freshness(),
        "results": [
            _result(cosine, payload, matched) for matched, cosine, payload in ranked
        ],
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
