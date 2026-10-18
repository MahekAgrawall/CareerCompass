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

Location, work arrangement, experience, employment type and posting date are
*store* filters, not post-filters: they travel to Qdrant as a payload filter, so
they narrow the whole collection and `matched` is an honest count of it. Running
them in Python over the ranked window instead would make every number on the page
a statement about the fifty postings the search happened to return.

Not every board publishes every one of those. That is a fact about the boards, so
the response carries it: `sources` says what each provider contributed to the last
harvest and why any is missing (`Freshness`-style sidecar data, not a guess from
the postings), so a page showing no Indian postings can say "Adzuna is not
configured on this server" rather than leaving a candidate to wonder.

The search box's words are a filter as well, and they are the one condition the
store cannot answer. Whether a posting *says* something is a rule about language
rather than a payload lookup, and the rule this app wants is wider than a
tokenizer's: whole words, their plurals and the compounds they introduce ("node"
finds "node.js") but never a longer word that merely starts the same ("java" must
not find JavaScript). So the eligible payloads are read out
(`vector_store.scroll_payloads`), narrowed here, and only then is the store asked
to rank what survived, restricted to those ids. Meaning orders the results; what
they say decides who is in them.

The places the search box suggests come from the collection too, and each count is
asked of that same filter (`locations`), because the boards publish free-text
locations — "Berlin" and "Berlin, Germany" are two strings for one city — and a
list built from the postings a previous search returned offered whatever ran last.

Every response also carries `freshness` (see the function): the date the postings
were harvested, and whether that is old enough to warn about. Live postings age —
a board keeps serving a listing after it is filled — so "12 of 87 matching" is
only half a sentence without "harvested 20 days ago".

The one filter that is not a field of a posting is `category`: what a listing
*actually is* is a verdict the classifier reached about its advert
(`services.classification`), so `category` narrows the candidates through that store
before anything is counted, and a listing nobody has read matches no category at
all. `classified` is reported beside `matched` for the same reason `freshness` is:
"4 of 61 matching" means something different when only 61 of 1,690 listings have
been read.
"""

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from services import classification, job_feed, vector_store

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

#: The employment vocabulary a client may ask for, and the board wording each
#: bucket is matched by. Like the experience buckets these are a *translation*, not
#: a lookup: the boards write "Full Time", "full-time" and "full time, permanent"
#: for the same thing, and Adzuna splits the answer in two (`contract_time` and
#: `contract_type`) while Arbeitnow sends a list. A bucket is therefore a set of
#: needles matched as tokens in the store's full-text condition — so "contract"
#: finds a contract advert and never "Contracting Officer".
EMPLOYMENT_TYPES = ("full_time", "part_time", "internship", "contract", "permanent")

_EMPLOYMENT_RULES: Dict[str, tuple] = {
    # Hyphenated and one-word spellings both tokenise to "full time", so one
    # needle covers them; "fulltime" is its own because nothing splits it.
    "full_time": ("full time", "fulltime"),
    "part_time": ("part time", "parttime"),
    "internship": ("intern", "internship", "working student", "werkstudent", "praktik", "trainee"),
    "contract": ("contract", "contractor", "freelance", "temporary"),
    "permanent": ("permanent",),
}

#: How far back "posted within" is offered, in days. A fixed short list rather than
#: a free number: the page asks whether a listing is recent enough to act on, and
#: the harvest only ever reads each board's newest rows anyway.
POSTED_WITHIN_DAYS = (7, 30, 90)

#: The payload fields the filters above read, and the index each needs. The
#: ingest applies this (`scripts.ingest_jobs`); the embedded store ignores
#: payload indexes, but a server-backed one needs the text indexes before it will
#: run a `MatchText` condition at all, and an integer index before it will run a
#: range.
FILTER_INDEXES = {
    "location": "text",
    "title": "text",
    "seniority": "text",
    "employment_type": "text",
    "remote": "bool",
    # The publication date, as an epoch — what "posted within a week" compares.
    # Written by the ingest (`job_feed.posting_payload`) and absent for a posting
    # the board never dated, which is what keeps an undated advert out of a date
    # filter instead of letting it pass on a technicality.
    "published_ts": "integer",
    # The ranking restricts the search to the postings the keywords kept (see
    # `_id_filter`). That condition is a payload lookup, so a server-backed store
    # wants an index on it; the embedded store scans either way.
    "id": "keyword",
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

#: The places the Jobs page offers as *preferences*, whatever the boards happen to
#: have published: the Indian market this app is built for, which the two boards
#: serve thinly — Himalayas publishes a few hundred India-open roles a month, and
#: Arbeitnow is a German board that carries almost none. Every one is counted by
#: the same store filter as any other option, but a preference is listed even at
#: zero, because a candidate looking for work at home deserves to be told what the
#: feed holds instead of finding the place silently missing from the page.
#:
#: Search-ready, unlike the questionnaire's `LOCATION_OPTIONS`: those entries are
#: hub *names* ("Mumbai / Pune", "Delhi / NCR / Gurgaon"), and the store's location
#: filter requires *every* word it is handed, so a hub name would ask the feed for
#: a single posting naming both cities and answer nothing. Each place here is one
#: word the boards write. The Indian market leads, in the order this app already
#: lists its hubs.
PREFERRED_JOB_LOCATIONS = (
    "India",
    "Bangalore",
    "Hyderabad",
    "Pune",
    "Mumbai",
    "Delhi",
    "Gurgaon",
    "Chennai",
)

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

#: What a posting's words are read from: the fields the payload displays, plus
#: `search_text` — the text the ingest embedded, so a keyword is judged against
#: what the job ad actually says rather than against the first 320 characters of
#: it. That field is absent until an index is built by an ingest that writes it,
#: which is why this is read as "whichever of these are there".
POSTING_TEXT_FIELDS = ("title", "company", "categories", "tags", "excerpt", "search_text")

#: The fields a keyword scan transfers: the words, plus the id the ranking is then
#: restricted to. Everything else in a payload would cross the wire to be dropped.
#:
#: The four label fields on the end are here for the classification filter rather
#: than the keyword one: a stored classification is checked for freshness against the
#: payload it is decorating (`classification.cached_for`), and a scan that did not
#: carry every field the classification was derived from would either have to skip
#: that check or invalidate every verdict it looked at. The scan is served from the
#: embedded store in this process, so the extra bytes are not billed to anyone.
SCAN_FIELDS = [
    "id",
    *POSTING_TEXT_FIELDS,
    "source",
    "location",
    "employment_type",
    "seniority",
]

#: How many postings one search reads to answer a keyword condition. A ceiling
#: rather than a page — the feed is capped by its own ingest — so a deployment
#: that ever outgrows it would have its counts describe the first this-many
#: postings rather than pretending to cover the collection.
KEYWORD_SCAN_LIMIT = 20000

#: Words a title should not be judged on: they are in half of them already.
_STOP_WORDS = {"a", "an", "and", "at", "for", "in", "of", "on", "or", "the", "to", "with"}


def _result(
    score: float,
    payload: Dict[str, Any],
    matched: Optional[List[str]] = None,
    verdict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """One stored posting, shaped for the response.

    Fields are picked one by one rather than forwarded wholesale: the stored
    payload stays free to grow, and a client cannot come to depend on internals
    that happen to be in the vector store.

    `verdict` is the listing's stored classification, when it has one. `None` means
    *not classified* while an Unclassified verdict is a full object — the two are
    different states (nobody has read this advert yet / the advert was read and could
    not be placed), and the card needs to tell them apart to know whether offering to
    classify it again makes sense.
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
        #: The board's own id for the listing, beside our namespaced `id`. Kept
        #: because a board's id is how the listing is identified *there*, which is
        #: what anyone reconciling the two would need.
        "source_job_id": str(payload.get("source_job_id") or ""),
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
        # Whether this advert has been read, and what it turned out to be. Absent
        # until someone asks (see `POST /jobs/classify` and `scripts.classify_jobs`):
        # the classification is never guessed here, only reported.
        "classification": verdict,
    }


def _by_category(
    candidates: List[Dict[str, Any]], category: str
) -> List[Dict[str, Any]]:
    """The candidates the classifier filed under one category, and only those.

    Filtered here rather than by the store, because the category is not a field of a
    posting: it is a *verdict* about one, held in the classification store and tied to
    the advert's text. It is read through `classification.cached_for`, so the filter
    uses the same freshness rule as everything else — a listing whose advert has been
    re-harvested since it was classified drops out of its old category instead of
    being filed under a reading that no longer describes it.

    A listing nobody has classified belongs to no category — not even "Other /
    Unclassified", which is a category the classifier *chose* for an advert it could
    not place, and not a bin for whatever is left over once the others are filtered.
    """
    verdicts = classification.cached_for(candidates)
    return [
        payload
        for payload in candidates
        if (verdicts.get(str(payload.get("id") or "")) or {}).get("primary_category")
        == category
    ]


def ranking_text(
    query: str = "",
    location: str = "",
    remote: Optional[bool] = None,
    experience: str = "",
    employment_type: str = "",
    posted_within_days: Optional[int] = None,
    category: str = "",
) -> str:
    """The text the ranking runs on: the caller's own words, or the filters.

    A search box is not the only way in — a candidate may want "every senior
    remote posting" and type nothing — so the filter terms stand in for the
    query when there are none. That keeps one ranking path, and `search_postings`
    echoes whichever text it used, so the response never claims a ranking the
    caller did not ask for.

    A bucket is spelled as the words it means ("full_time" -> "full time"), not as
    the slug: this text is embedded and compared by meaning, and an underscore is
    not a word.

    The category joins the words like the other filters do. It names a phrase a job
    advert genuinely uses ("Backend Development"), so a browse by category alone is
    ranked by something better than nothing — and where the phrase means little
    ("Other / Unclassified"), the ranking is merely uninformative over a set the
    filter has already decided, not wrong.

    The date filter is the one dimension that names no words at all, and the store
    refuses an empty query outright (see `vector_store.search_records`) — so a
    date-only browse is given the phrase that describes it. Without that, the one
    filter a candidate can set with nothing else (\"newest first\") would answer
    with an empty page.
    """
    parts = [
        str(query or "").strip(),
        str(location or "").strip(),
        str(category or "").strip(),
    ]
    if remote is not None:
        parts.append("remote" if remote else "on-site")
    if experience:
        parts.append(str(experience).strip())
    if employment_type:
        parts.append(str(employment_type).replace("_", " ").strip())
    words = [part for part in parts if part]
    if not words and posted_within_days:
        words.append("recent jobs")
    return " ".join(words)


def published_floor(days: int) -> int:
    """The epoch a "posted within" filter counts from: midnight, `days` ago.

    Whole days rather than a timestamp to the second, because a posting's
    `published_ts` is the date the board gave (see `job_feed.published_epoch`) and
    comparing a date against a clock would drop a posting dated exactly `days` ago
    depending on what time of day it was read. The window is therefore at least as
    wide as it says and never narrower.
    """
    today = datetime.now(timezone.utc).date()
    return int(
        datetime.combine(today - timedelta(days=days), datetime.min.time())
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )


def posting_filter(
    location: str = "",
    remote: Optional[bool] = None,
    experience: str = "",
    employment_type: str = "",
    posted_within_days: Optional[int] = None,
):
    """The Qdrant filter behind the Jobs page, or `None` when nothing narrows.

    Each dimension is a nested `should`, so the conditions *within* one dimension
    are alternatives ("Berlin" or a remote flag, "full time" or "fulltime") while
    the dimensions themselves are all required. An unrecognised experience or
    employment bucket is ignored here rather than raising: the endpoint types them
    as literals, so a client cannot get this far with one, and a store filter is the
    wrong place to answer 500s.
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

    hiring = _EMPLOYMENT_RULES.get(str(employment_type or "").strip().lower())
    if hiring:
        must.append(
            models.Filter(
                should=[
                    models.FieldCondition(
                        key="employment_type", match=models.MatchText(text=word)
                    )
                    for word in hiring
                ]
            )
        )

    if posted_within_days and posted_within_days > 0:
        must.append(
            models.FieldCondition(
                key="published_ts",
                range=models.Range(gte=published_floor(int(posted_within_days))),
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
    """The places the Jobs page offers: the collection's own places, and India's.

    The location field is free text over the boards' wording, which is not a
    vocabulary — and the page used to fill its suggestions from the fifty postings
    a previous search happened to return, so it offered whatever ran last rather
    than what exists. These options come from the collection itself.

    Every count is *asked of the store filter a search would apply*, never guessed
    from the text: the number beside "Germany" is the number of postings clicking
    it will return, which is the `matched` that search then reports. A candidate
    the filter cannot match — a hyphenated district the tokenizer splits, say —
    counts zero and is dropped rather than offered as a dead end.

    Two lists come back, and the difference between them is the point:

    * `locations` — the vocabulary the collection itself names, as it always was;
    * `preferred` — the Indian market this app is built for (see
      `PREFERRED_JOB_LOCATIONS`), counted by that same filter but listed even when
      it counts nothing, because both boards publish into India thinly and a page
      that answered that with silence would be the least honest part of this.
      "India" is usually the live one; the cities say zero until a harvest finds
      them.

    Without an index this answers `available: false` and no options of either
    kind, like every other read here. Reads up to `LOCATION_SCAN_LIMIT` postings,
    and keeps the answer until the index's recorded state changes.
    """
    if not (
        vector_store.is_available()
        and vector_store.collection_exists(vector_store.JOBS_COLLECTION)
    ):
        return {"available": False, "locations": [], "preferred": []}

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

    # The preferences keep the order they are declared in rather than being ranked
    # by count: this list is a judgement about what the app offers, not a reading
    # of the boards, so a city the feed does not carry yet should not also be
    # buried at the bottom of it.
    preferred = [
        {
            "value": value,
            "count": vector_store.count_points(
                vector_store.JOBS_COLLECTION, posting_filter(location=value)
            ),
        }
        for value in PREFERRED_JOB_LOCATIONS
    ]

    answer = {
        "available": True,
        "locations": options[:limit],
        "preferred": preferred,
    }
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


def source_status(meta: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """What each board contributed to the last harvest, and why any is missing.

    Read from the same sidecar as `freshness`, and for the same reason it exists:
    a board that was never reached and a board that was reached and had nothing new
    both leave the index short, and only the ingest knows which happened. That
    distinction is the whole point — a client can then say *"Adzuna is not
    configured on this server"* instead of showing a feed with no Indian postings
    in it and no explanation for the absence.

    A board that loaded but contributed nothing is reported too, with `postings: 0`
    and no error: that is what a market query that found nothing looks like, and it
    should be as visible as a failure.

    An index built before any of this was recorded answers an empty list, which a
    client reads as "nothing to report" rather than as a silent all-clear.

    The error text is redacted on the way out (`job_feed.without_credentials`): a
    board that rejects the harvest's key quotes the request's whole URL in its
    failure, and that includes the query string the key rides in. This endpoint is
    unauthenticated, so whatever a harvest recorded is scrubbed before it is served
    — including an index written before the feed stopped recording the query at all.
    """
    meta = vector_store.recorded_meta(vector_store.JOBS_COLLECTION) if meta is None else meta
    recorded = meta.get("sources")
    if not isinstance(recorded, list):
        return []
    status: List[Dict[str, Any]] = []
    for entry in recorded:
        if not isinstance(entry, dict):
            continue
        source = str(entry.get("source") or "")
        if not source:
            continue
        try:
            count = int(entry.get("postings") or 0)
        except (TypeError, ValueError):
            count = 0
        status.append(
            {
                "source": source,
                "postings": max(0, count),
                "error": job_feed.without_credentials(str(entry.get("error") or "")),
            }
        )
    return status


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


def matches_token(term: str, token: str) -> bool:
    """Whether one of the query's words is one of the posting's.

    Whole words, with two deliberate allowances: a plural counts ("developer"
    finds "developers") and a compound the word introduces counts ("node" finds
    "node.js", "front" finds "front-end"). What is *not* allowed is a longer word
    that merely starts the same way — a search for "java" must not answer with
    JavaScript, and "data" must not answer with databases.
    """
    if token == term:
        return True
    if not token.startswith(term):
        return False
    rest = token[len(term):]
    if rest in ("s", "es"):
        return True
    return rest[0] in ".-_/"


def mentions(words: set, term: str) -> bool:
    """Whether those words carry one of the query's."""
    return any(matches_token(term, token) for token in words)


def posting_words(payload: Dict[str, Any]) -> set:
    """Every word a posting says: what a keyword is matched against.

    The displayable fields plus `search_text` (see `POSTING_TEXT_FIELDS`), because
    a job ad says what it is offering in its description and not only in its
    title. Set semantics: a word said twice is still the word it says.
    """
    parts: List[str] = []
    for field in POSTING_TEXT_FIELDS:
        value = payload.get(field)
        if isinstance(value, (list, tuple)):
            parts.extend(str(item) for item in value)
        elif value:
            parts.append(str(value))
    return _words(" ".join(parts))


def title_matches(query: str, title: str) -> List[str]:
    """Which query words that title carries — whole words, as `matches_token`."""
    words = _words(title)
    return [term for term in query_terms(query) if mentions(words, term)]


def _narrow(
    candidates: List[Dict[str, Any]], terms: List[str]
) -> Tuple[List[Dict[str, Any]], bool]:
    """The postings that say every one of `terms` — or, when none does, any.

    Returns `(kept, relaxed)`. Requiring all of them is what makes the search box
    a filter: "java" cannot answer with a listing that never mentions Java. The
    relaxation is the safety valve, not a nicety — a candidate's goal sentence is
    not a keyword, and a page that answers "nothing found" to a reasonable query
    is worse than one that says it had to loosen. It is *reported* rather than
    silent, because a search that quietly drops half the words is lying about what
    it searched.

    `relaxed` is true only when dropping to "any" actually found something. A query
    no posting mentions at all is a plain miss, not a loosening: flagging it would
    tell the page every word was dropped to reach rows that do not exist.
    """
    if not terms:
        return list(candidates), False
    said = [(payload, posting_words(payload)) for payload in candidates]
    strict = [
        payload for payload, words in said if all(mentions(words, term) for term in terms)
    ]
    if strict:
        return strict, False
    loose = [
        payload for payload, words in said if any(mentions(words, term) for term in terms)
    ]
    return loose, bool(loose)


def _id_filter(ids: List[str]):
    """A store condition keeping only these postings, for the ranking to run in.

    The keyword decision is already made (see `_narrow`); this is how the semantic
    ranking is told *which* postings survived it, so the store never has to know
    the matching rules.
    """
    from qdrant_client import models

    return models.Filter(
        must=[models.FieldCondition(key="id", match=models.MatchAny(any=ids))]
    )


def _rank(hits: List, query: str, limit: int) -> List:
    """The store's hits, resorted so a posting that says your words comes first.

    Three keys, in this order: how many of the query's words the posting's *title*
    carries, how many it carries *anywhere* in its text, and the store's own cosine.
    A single blended score was tried first and thrown away — no fixed weight suits
    both the offline embedder, whose term frequency swamps everything, and a hosted
    one whose cosines barely move. Counting words needs no weight, and the live
    index needs it: for "python" it puts a German facilities-maintenance listing
    second, in front of postings that actually name the language.

    The words come from the *search box only*, never from the filters: an earlier
    version ranked on the location too, so searching "java" in Amsterdam answered
    with titles containing "Amsterdam". A filter has already decided what is
    eligible; letting it also decide the order contradicts what was asked for.

    Every tier is a no-op on a query none of the postings carry: they all land in
    one tier and the stable sort returns the index's own order untouched.

    Returned as `(matched words, cosine, payload)`, wider than the page because the
    window is what lets a posting climb at all.
    """
    terms = query_terms(query)
    scored = []
    for score, payload in hits:
        said = posting_words(payload)
        in_title = _words(payload.get("title") or "")
        # `matched` is what the *card* reports, so it stays title-only: the words
        # the posting says in the body explain an ordering nobody can see, and
        # reporting them as a title match would be a lie about the posting.
        matched = [term for term in terms if mentions(in_title, term)]
        scored.append(
            (
                -len(matched),
                -sum(1 for term in terms if mentions(said, term)),
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
    employment_type: str = "",
    posted_within_days: Optional[int] = None,
    category: str = "",
) -> Dict[str, Any]:
    """The `job_role` postings that satisfy the search, nearest first.

    The words are a **filter**, not a ranking hint: a posting comes back only when
    it says every one of them (as whole words — see `matches_token`), so "java"
    cannot answer with a listing that never mentions Java. `matched` counts what
    the words *and* the filters leave in the whole collection, as opposed to
    `count`, which is how many of those came back in this page. Both are reported
    so a client can show "12 of 87 matching, 951 indexed" without implying it
    inspected more than it did.

    The structured filters are the store's (see `posting_filter`), including the
    two that are not a vocabulary lookup: `employment_type` translates the boards'
    wording for how a job hires ("full time, permanent" answers both buckets), and
    `posted_within_days` compares the publication date a board gave. A board that
    published neither — Adzuna states no pay period and no remote flag, and no
    board but the catalogs state experience — simply does not match those filters,
    which is why the response carries `sources`.

    The store still does the ranking: the surviving postings are ordered by the
    index's meaning, and `_rank` lifts ones whose *title* carries a word. `relaxed`
    says no posting could satisfy every word, so only some were required (see
    `_narrow`) — reported rather than silent, because a page that quietly searches
    for less than it was asked to is lying about what it found. A query no posting
    mentions at all comes back `relaxed: false` with no rows: that is a miss, not a
    loosening.

    The store is asked for a wider window than the page and `_rank` cuts it, so a
    posting whose title carries the query can be lifted over one the vector store
    merely placed nearer — the difference between a search box and a similarity
    list.

    `category` is the one filter the store cannot apply: it is a *classification* of
    the advert rather than a field on it, so the scanned candidates are narrowed
    through the classification store (see `_by_category`) before the width of the
    collection is counted. On a feed where only some listings have been classified,
    `matched` therefore counts the classified part of the collection and `classified`
    says how much of it that is — "4 of 61 matching, 61 of 1,690 classified", never a
    total that implies the whole feed was read.
    """
    text = ranking_text(
        query,
        location,
        remote,
        experience,
        employment_type,
        posted_within_days,
        category,
    )
    terms = query_terms(query)
    available = jobs_available()
    # Built only when there is a store to filter. `posting_filter` needs the
    # qdrant-client models, and `is_available()` only proves an index *directory*
    # exists, so a deployment with the data but without the client used to raise
    # here — a 500 where the module promises `available: false` and no rows, the
    # way `search_for_role` answers. The filters have nothing to narrow without
    # an index anyway.
    filters = (
        posting_filter(location, remote, experience, employment_type, posted_within_days)
        if available
        else None
    )

    kept: Optional[List[Dict[str, Any]]] = None
    relaxed = False
    if available:
        candidates = vector_store.scroll_payloads(
            vector_store.JOBS_COLLECTION,
            filters,
            KEYWORD_SCAN_LIMIT,
            keys=SCAN_FIELDS,
        )
        if category:
            candidates = _by_category(candidates, category)
        kept, relaxed = _narrow(candidates, terms)

    # Both conditions are decided here rather than by the store, so both travel to
    # it as the set of ids to rank inside. `category` counts as well as `terms`: a
    # category no classified posting matches has to answer with no rows at all, not
    # with the store's nearest rows from outside it.
    ids = (
        [str(payload.get("id") or "") for payload in kept or []]
        if terms or category
        else []
    )
    # With words in play the store ranks *inside* them: the other filters are
    # already applied to the set, and a store-side keyword condition would put the
    # matching rules in a tokenizer rather than here (see `matches_token`).
    query_filter = _id_filter(ids) if ids else filters
    hits: List = (
        vector_store.search_records(
            vector_store.JOBS_COLLECTION,
            text,
            limit=min(limit * RANK_WINDOW, MAX_RANK_WINDOW),
            query_filter=query_filter,
        )
        if available and (ids or not (terms or category))
        else []
    )
    ranked = _rank(hits, query, limit)
    # The verdicts for this page, looked up once for the whole page rather than per
    # card, and only for the rows being returned: classifying is the caller's to
    # ask for (`POST /jobs/classify`), and a search never spends a model call.
    verdicts = classification.cached_for([payload for _, _, payload in ranked])
    return {
        "query": text,
        "available": available,
        "relaxed": relaxed,
        "count": len(ranked),
        "matched": len(kept or []),
        "classified": classification.stored_count(),
        "indexed": (
            vector_store.count_points(vector_store.JOBS_COLLECTION) if available else 0
        ),
        "freshness": freshness(),
        # What each board contributed last time, so a feed that is missing a
        # provider can say which and why (see `source_status`).
        "sources": source_status(),
        "results": [
            _result(
                cosine,
                payload,
                matched,
                verdicts.get(str(payload.get("id") or "")),
            )
            for matched, cosine, payload in ranked
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
    `available: false`, never an invented fallback. The rows carry their stored
    classifications when they have them, so the same posting does not look
    classified on one page and unread on another.
    """
    available = jobs_available()
    hits: List = (
        vector_store.search_records(
            vector_store.JOBS_COLLECTION, role_query(role, profile), limit=limit
        )
        if available
        else []
    )
    verdicts = classification.cached_for([payload for _, payload in hits])
    return {
        "role_id": str(role.get("id") or ""),
        "role_title": str(role.get("title") or ""),
        "available": available,
        "count": len(hits),
        "results": [
            _result(score, payload, verdict=verdicts.get(str(payload.get("id") or "")))
            for score, payload in hits
        ],
    }


def posting_by_id(listing_id: str) -> Optional[Dict[str, Any]]:
    """One stored posting, by the namespaced id the feed uses, or None.

    The whole payload, not the display subset: whoever asks for a posting by id is
    about to *do* something with it (classify it), and `_result` has already thrown
    away the text the classification reads.

    None covers both "no such listing" and "no index" — the two are told apart by the
    caller with `jobs_available`, which is the same pair of facts every read here
    reports, so a caller can answer 503 for a store that was never built and 404 for
    an id that is not in it.
    """
    if not listing_id:
        return None
    rows = vector_store.scroll_payloads(
        vector_store.JOBS_COLLECTION, _id_filter([listing_id]), 1
    )
    return rows[0] if rows else None


def jobs_available() -> bool:
    """Whether the `job_role` index is there to be read at all.

    The check every read in this module makes before it answers; exposed because a
    caller that is about to explain an empty answer needs to know which of the two
    empty answers it is giving.
    """
    return vector_store.is_available() and vector_store.collection_exists(
        vector_store.JOBS_COLLECTION
    )
