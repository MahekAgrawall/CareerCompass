"""What a live listing actually is: an AI reading of the advert, kept once.

A board's title is written to attract clicks, not to describe a job, so the
classification is read from the advert's own text — description and requirements —
by `ai_service.classify_listing`, and placed in the declared vocabulary
(`config.CANONICAL_ROLES`). What this module owns is everything *around* that call:

* what the advert is, as text the model can read and the cache can fingerprint;
* the rule that says an advert too thin to describe a job is not a classification
  problem at all, so no call is spent on it and no family is invented for it;
* the same treatment for an answer the model itself hedges, or one that could not be
  read — reported as Unclassified, never dressed up as a verdict;
* the store that stops the same advert being classified on every page load.

The unit of cache is the listing, not the request: a classification is a reading of
a public advert, so the first caller to ask for one pays for it and everyone after
them, of any account, reads it. It is invalidated by *reading through* three keys —
the advert's content hash, the model, and the prompt fingerprint — so re-harvested
text, a pinned model, or edited prompt wording all miss the cache and are done
again, without a deletion step and without ever mixing two recipes in one row.

Transient trouble is deliberately not cached. "The API was unconfigured", "the
answer could not be read" and "the call failed" are facts about a moment, not about
the advert, so they come back as Unclassified for that request and are asked again
next time. Only verdicts that would repeat — a placed family, an advert the model
declined to place, an advert too thin to place — are written down.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app_logging import get_logger
from config import (
    OTHER_CATEGORY,
    ROLE_CATEGORY_OF,
    SENIORITY_LEVELS,
    UNCLASSIFIED_ROLE,
    WORK_ARRANGEMENTS,
)
from database.db import get_connection
from services import ai_service, sanitize

log = get_logger("careercompass.classification")

#: How much of the advert is put in front of the model. The payload holds the
#: description truncated for display (`excerpt`) and the fuller text that was
#: embedded (`search_text`), so this is a ceiling on text that is already bounded —
#: classification never grows what the ingest chose to keep, and the whole advert is
#: never re-fetched for it.
ADVERT_TEXT_LIMIT = 1500

#: Below this, the advert is not describing a job however promising its title is.
#: Measured on `excerpt` — the *description* the payload keeps — because the labelled
#: metadata lines that surround it in `search_text` would make a title-only advert
#: look like a described one. No model call is made below the threshold: an advert
#: that says nothing cannot be classified by asking more expensively.
MIN_DESCRIPTION_CHARS = 120

#: The confidence under which a placed answer is reported as Unclassified. The same
#: number the system prompt quotes, so the rule the model is given and the rule
#: applied to its answer are one rule rather than two that drift apart.
CONFIDENCE_FLOOR = 0.55

MAX_LISTING_ID_CHARS = 200
MAX_TITLE_CHARS = 200
MAX_EXPLANATION_CHARS = 300
MAX_SKILLS = 12
MAX_RELATED_TITLES = 6
MAX_EXPERIENCE_YEARS = 50.0

#: How many ids one SQL lookup carries. SQLite's parameter limit is 999 on older
#: builds, so a lookup that may cover a whole scanned feed is chunked rather than
#: left to work on this machine's build and fail on another.
_ID_CHUNK = 400

#: How many postings one `--from-index` read transfers. A ceiling rather than a
#: target, like the keyword scan's: the feed is capped by its own ingest, so a
#: deployment that ever outgrew this would pre-fill the newest this-many listings
#: rather than silently appearing to have covered the collection.
MAX_SCAN_POSTINGS = 20000

#: Why a listing has no family, as a stable kind beside the sentence a card prints.
#: The sentence is for a candidate; the kind is for the code that counts them (the
#: pre-fill script's summary, and any later "why are these unclassified" view), which
#: should not have to parse prose to tell "the advert said nothing" from "the model
#: was unsure". Kept apart for exactly that reason: the wording is free to improve
#: without any counting changing meaning.
KIND_TOO_THIN = "too_thin"
KIND_DECLINED = "declined"
KIND_UNSURE = "unsure"
KIND_UNREADABLE = "unreadable"
KIND_UNREACHABLE = "unreachable"

REASON_TOO_THIN = "the advert does not describe the job, so there is nothing to classify"
REASON_DECLINED = "the advert does not fit any declared role family"
REASON_UNSURE = "the advert was not clear enough to place (the AI's confidence was {confidence:.2f})"
REASON_UNREADABLE = "the AI's answer could not be read as a classification"
REASON_UNREACHABLE = "the classification service could not be reached"

#: The kind -> sentence table, so the two can never drift apart. `KIND_UNSURE` holds
#: a template: it is the only one that quotes a number back.
UNCLASSIFIED_REASONS = {
    KIND_TOO_THIN: REASON_TOO_THIN,
    KIND_DECLINED: REASON_DECLINED,
    KIND_UNSURE: REASON_UNSURE,
    KIND_UNREADABLE: REASON_UNREADABLE,
    KIND_UNREACHABLE: REASON_UNREACHABLE,
}

#: The kinds that are facts about a *moment* rather than about the advert, and are
#: therefore reported but never stored (see the module docstring). Everything else is
#: a verdict that would repeat, so it is cached.
TRANSIENT_KINDS = (KIND_UNREADABLE, KIND_UNREACHABLE)


class MinimumExperience(BaseModel):
    """How much experience the advert asks for, as the advert stated it."""

    years: Optional[float] = None
    as_written: str = ""


class ListingClassification(BaseModel):
    """One listing's stored verdict: the eleven asked-for fields and its provenance.

    The eleven are what the requirement names. The rest is what makes the answer
    checkable later — which listing, which board, which model, which prompt wording,
    when — plus the two things a client needs to tell a real verdict from a
    non-verdict: `unclassified_reason` (empty when the listing *was* placed) and
    `cached` (this read came from the store rather than from the model).

    `primary_category` is derived from `canonical_role` through the declared
    vocabulary rather than taken from the model's own pairing, so the two fields
    cannot contradict each other: the role is the finer claim, and the vocabulary
    already says which category it belongs to.
    """

    primary_category: str = OTHER_CATEGORY
    canonical_role: str = UNCLASSIFIED_ROLE
    original_title: str = ""
    related_role_titles: List[str] = []
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    minimum_experience: MinimumExperience = Field(default_factory=MinimumExperience)
    seniority_level: str = "unknown"
    work_arrangement: str = "unspecified"
    classification_confidence: float = 0.0
    #: One line from the model about *why*: what in the advert made it that role, or —
    #: for an advert it declined to place — what was missing or why no family fits.
    #: Empty when it was not placed for another reason (too thin, too unsure).
    short_match_explanation: str = ""
    listing_id: str = ""
    source: str = ""
    model: str = ""
    prompt_version: str = ""
    classified_at: str = ""
    cached: bool = False
    #: Empty when the listing was placed. When it was not: the kind (`KIND_*`, for
    #: code that counts) and the sentence (`unclassified_reason`, for a reader).
    unclassified_kind: str = ""
    unclassified_reason: str = ""

    @property
    def is_classified(self) -> bool:
        """True when the advert was placed in a family, not reported as unplaceable."""
        return self.canonical_role != UNCLASSIFIED_ROLE


def advert_values(payload: Dict[str, Any]) -> Dict[str, str]:
    """The advert as the model receives it, and as the cache fingerprints it.

    One dict, used for both, so a cache hit is provably the same question: whatever
    is not in here cannot change a verdict, and whatever *is* in here invalidates one
    when it changes.

    Every value is scrubbed first. A job advert is text a stranger wrote for a
    reason, and it is read by a model that also takes instructions — so it travels as
    flattened, length-capped data inside the user half of the prompt, with the system
    half (which states that the advert is data) unaffected by anything in it. The
    label fields matter as much as the body: a board's own seniority and category tags
    are legitimate evidence about a listing, and a board that relabels a posting
    should get it re-read.

    Missing fields become short stand-ins ("not stated") rather than vanishing, so
    the model is told what the board did not publish instead of left to assume.
    """
    return {
        "source": sanitize.single_line(payload.get("source"), 40) or "unknown",
        "title": sanitize.single_line(payload.get("title"), MAX_TITLE_CHARS)
        or "(untitled)",
        "company": sanitize.single_line(payload.get("company"), 120) or "not stated",
        "location": sanitize.single_line(payload.get("location"), 120) or "not stated",
        "employment_type": sanitize.single_line(payload.get("employment_type"), 60)
        or "not stated",
        "seniority": ", ".join(sanitize.labels(payload.get("seniority"))) or "not stated",
        "categories": ", ".join(sanitize.labels(payload.get("categories")))
        or "none published",
        "advert_text": advert_text(payload),
    }


def advert_text(payload: Dict[str, Any]) -> str:
    """The advert's own words, as far as the app holds them.

    `search_text` is the fuller of the two (the ingest keeps an excerpt for display
    and a longer one for embedding), and it falls back to `excerpt` so a payload
    written before that field existed still classifies.

    This is the honest limit of the classification: a board that publishes a
    two-line advert — Adzuna truncates descriptions at 500 characters — gives the
    model two lines to read, which is why thin adverts come back Unclassified
    instead of being padded with what the title implies.
    """
    raw = payload.get("search_text") or payload.get("excerpt") or ""
    return sanitize.single_line(raw, ADVERT_TEXT_LIMIT)


def describes_a_job(payload: Dict[str, Any]) -> bool:
    """Whether the advert says enough about the job to place it honestly.

    Judged on the description rather than on everything the payload holds, because a
    title on its own is the one input this feature exists to *not* trust: a listing
    called "Senior Backend Engineer" with no advert behind it has no requirements to
    read, and the correct answer for it is that there is nothing to classify.
    """
    return len(sanitize.single_line(payload.get("excerpt"), 2000)) >= MIN_DESCRIPTION_CHARS


def content_hash(values: Dict[str, str]) -> str:
    """A stable fingerprint of exactly what would be sent to the model."""
    material = json.dumps(values, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def prompt_version() -> str:
    """The prompt wording a verdict was produced under."""
    return ai_service.classify_prompt_version()


def stored(payload: Dict[str, Any], force: bool = False) -> Optional[Dict[str, Any]]:
    """The verdict already written down for this listing, or None.

    A pure read: no model, no writes, and no judgement about the advert — the caller
    that wants to know what is *in the store* asks this (the pre-fill script, to work
    out what is left to do), and the caller that wants to know what can be answered
    without spending anything asks `without_model` instead.

    `force` says the caller wants a fresh reading regardless, so nothing to hand back.
    """
    if force:
        return None
    listing_id = sanitize.single_line(payload.get("id"), MAX_LISTING_ID_CHARS)
    row = _cached(listing_id, content_hash(advert_values(payload)))
    if row is None:
        return None
    return {**row, "cached": True}


def without_model(
    payload: Dict[str, Any], force: bool = False
) -> Optional[Dict[str, Any]]:
    """The verdict this listing can be given without asking the model — or None.

    Two of them. The first is the *stored* verdict (see `stored`), which is what makes
    a page view free: somebody has already paid for this advert. The second is one the
    advert decides on its own — an advert that does not describe a job has nothing in
    it to read, so there is nothing to ask, and that verdict is written down the first
    time so the next reader is told *why* the listing is unclassified instead of
    finding it simply unread.

    The caller that meters AI calls needs exactly this decision before it spends
    anything (see `POST /jobs/classify`), which is why it is a function rather than a
    branch inside `classify_posting`.

    `force` bypasses the store, not the advert: re-reading an advert that describes
    nothing produces the same reading, so there is no model to send it to.
    """
    settled = stored(payload, force=force)
    if settled is not None:
        return settled

    listing_id = sanitize.single_line(payload.get("id"), MAX_LISTING_ID_CHARS)
    if describes_a_job(payload):
        return None

    record = _unclassified(listing_id, payload, KIND_TOO_THIN)
    _store(record, content_hash(advert_values(payload)))
    return record.model_dump()


def classify_posting(payload: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    """The verdict for one listing, from the store when it is already known.

    `force` re-asks the model even when the store would answer — the escape hatch for
    a verdict that is stale in a way the keys cannot see (a prompt whose meaning
    changed without its text changing, or a listing the model simply got wrong).

    A missing API key is raised, not swallowed (`AIConfigurationError`): it is the
    deployment's problem and the API answers 503 for it. Everything else that can go
    wrong is reported as Unclassified with the reason attached, because a listing
    with no classification is still a listing and a page of them is not an error.
    """
    settled = without_model(payload, force=force)
    if settled is not None:
        return settled

    listing_id = sanitize.single_line(payload.get("id"), MAX_LISTING_ID_CHARS)
    values = advert_values(payload)

    try:
        answer = ai_service.classify_listing(values)
    except ai_service.AIConfigurationError:
        raise
    except ai_service.ListingClassificationError as exc:
        log.warning("listing %s: unreadable classification answer: %s", listing_id, exc)
        return _unclassified(
            listing_id, payload, KIND_UNREADABLE, used_model=True
        ).model_dump()
    except Exception as exc:  # network, quota, a changed SDK — all momentary
        log.warning("listing %s: classification call failed: %s", listing_id, exc)
        return _unclassified(
            listing_id, payload, KIND_UNREACHABLE, used_model=True
        ).model_dump()

    record = _verdict_from(answer, payload, listing_id)
    _store(record, content_hash(values))
    return record.model_dump()


def cached_for(payloads: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The stored verdicts for these listings, keyed by listing id.

    Takes the payloads rather than their ids because freshness is decided from the
    advert itself: the same `advert_values`/`content_hash` pair that decides a cache
    hit on demand is applied here, so a listing whose advert has been re-harvested
    into different text is simply *absent* from the returned map — and is therefore
    presented as unclassified — rather than shown under a verdict that no longer
    describes it.
    """
    wanted: Dict[str, str] = {}
    for payload in payloads:
        listing_id = sanitize.single_line(payload.get("id"), MAX_LISTING_ID_CHARS)
        if listing_id:
            wanted[listing_id] = content_hash(advert_values(payload))
    if not wanted:
        return {}

    verdicts: Dict[str, Dict[str, Any]] = {}
    for listing_id, row in _rows(list(wanted)).items():
        if _still_valid(row, wanted[listing_id]):
            verdicts[listing_id] = {
                **json.loads(row["classification_json"]),
                "cached": True,
            }
    return verdicts


def stored_count() -> int:
    """How many listings the classifier holds a verdict for.

    Counted over the store rather than the pages, so it is what a response means by
    "classified": listings that have been read — including the ones the classifier
    read and reported as Unclassified, which is a verdict too. It is not a promise
    that every one of them would be placed today; a re-harvested advert is re-read
    on its next page view.
    """
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT COUNT(*) AS total FROM listing_classifications;")
        row = cursor.fetchone()
        return int(row["total"]) if row else 0
    finally:
        conn.close()


def _verdict_from(
    answer: ai_service.ListingAnswer, payload: Dict[str, Any], listing_id: str
) -> ListingClassification:
    """The model's answer as a stored verdict — or as Unclassified, if it hedged.

    Two ways an answer becomes Unclassified rather than a classification:

    * the model itself declined, choosing the Unclassified line — it read the advert
      and judged there is not enough in it, which is an answer and is kept; and
    * it named a family but with confidence under the floor — a guess, which is
      *not* kept: every classification field is emptied so nothing half-believed is
      shown, and the number that caused it is kept visible instead.

    Neither is re-asked. Re-rolling a hedged answer only asks for a more confident
    one, which is how a classifier talks itself into inventing a job.
    """
    confidence = min(max(float(answer.classification_confidence), 0.0), 1.0)
    role = answer.resolved_role() or UNCLASSIFIED_ROLE

    if role == UNCLASSIFIED_ROLE:
        # The model's own sentence is kept here, and only here: it is the one place it
        # can say *why* (an advert too vague to read, or a sales job outside the
        # declared families), and "we could not place it" on its own makes a reader
        # guess between the two. Every classification field stays empty — the
        # explanation is not a classification.
        return _unclassified(
            listing_id,
            payload,
            KIND_DECLINED,
            confidence=confidence,
            used_model=True,
            explanation=sanitize.single_line(
                answer.short_match_explanation, MAX_EXPLANATION_CHARS
            ),
        )
    if confidence < CONFIDENCE_FLOOR:
        return _unclassified(
            listing_id,
            payload,
            KIND_UNSURE,
            confidence=confidence,
            used_model=True,
        )

    required = sanitize.labels(answer.required_skills, limit=MAX_SKILLS)
    # A skill the advert demands is not also a bonus: where the model lists it twice,
    # the stricter reading is the honest one and the optional list loses the repeat.
    demanded = {skill.casefold() for skill in required}
    preferred = [
        skill
        for skill in sanitize.labels(answer.preferred_skills, limit=MAX_SKILLS)
        if skill.casefold() not in demanded
    ]
    related = [
        title
        for title in sanitize.labels(answer.related_role_titles, limit=MAX_RELATED_TITLES)
        if title.casefold() != role.casefold()
    ]

    return ListingClassification(
        primary_category=ROLE_CATEGORY_OF[role],
        canonical_role=role,
        # The advert's own title, not the model's transcription of it: a card shows
        # the title as published, and a retyped one is a chance to get it wrong.
        original_title=sanitize.single_line(payload.get("title"), MAX_TITLE_CHARS),
        related_role_titles=related,
        required_skills=required,
        preferred_skills=preferred,
        minimum_experience=MinimumExperience(
            years=_stated_years(answer.minimum_experience.years),
            as_written=sanitize.single_line(answer.minimum_experience.as_written, 80),
        ),
        # An answer outside these two vocabularies is not a new bucket to reason
        # about, it is one we cannot use — so it degrades to the "not stated" value
        # rather than being stored as a seventh seniority level of its own.
        seniority_level=(
            answer.seniority_level.strip().casefold()
            if answer.seniority_level.strip().casefold() in SENIORITY_LEVELS
            else "unknown"
        ),
        work_arrangement=(
            answer.work_arrangement.strip().casefold()
            if answer.work_arrangement.strip().casefold() in WORK_ARRANGEMENTS
            else "unspecified"
        ),
        classification_confidence=confidence,
        short_match_explanation=sanitize.single_line(
            answer.short_match_explanation, MAX_EXPLANATION_CHARS
        ),
        listing_id=listing_id,
        source=sanitize.single_line(payload.get("source"), 40),
        model=ai_service.MODEL_NAME,
        prompt_version=prompt_version(),
        classified_at=_now(),
    )


def _stated_years(years: Optional[float]) -> Optional[float]:
    """The number of years, or nothing at all when it is not a plausible figure.

    A negative or absurd figure (a decade-old advert asking for "40 years of
    Kubernetes") is a data error, and quoting it back as fact is worse than admitting
    the advert did not say something usable. The ceiling is what makes that admission
    possible without judgement calls about what is "reasonable".
    """
    if years is None:
        return None
    try:
        value = float(years)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= MAX_EXPERIENCE_YEARS else None


def _unclassified(
    listing_id: str,
    payload: Dict[str, Any],
    kind: str,
    confidence: float = 0.0,
    used_model: bool = False,
    explanation: str = "",
) -> ListingClassification:
    """A listing the classifier could not place — still a verdict, just a negative one.

    Every classification field is emptied rather than left partly filled: half a
    classification ("Backend Development, but we are not sure") is exactly the
    invented detail the requirement forbids. Either the advert was placed in a family
    or it is reported as unplaced, with a reason a reader can act on and a kind the
    code can count.

    `explanation` is the model's own sentence, passed only where it explains the
    *decline* (see `_verdict_from`) and left empty everywhere else, so an unplaced
    listing never carries a sentence about a family it was not placed in.

    `used_model` records whether a model was consulted at all. An advert too thin to
    classify never reached one, and its row says so by naming no model — which is
    also what lets it stay valid across a model change.
    """
    reason = UNCLASSIFIED_REASONS[kind]
    if "{confidence" in reason:
        reason = reason.format(confidence=confidence)
    return ListingClassification(
        primary_category=OTHER_CATEGORY,
        canonical_role=UNCLASSIFIED_ROLE,
        original_title=sanitize.single_line(payload.get("title"), MAX_TITLE_CHARS),
        classification_confidence=confidence,
        short_match_explanation=explanation,
        listing_id=listing_id,
        source=sanitize.single_line(payload.get("source"), 40),
        model=ai_service.MODEL_NAME if used_model else "",
        prompt_version=prompt_version() if used_model else "",
        classified_at=_now(),
        unclassified_kind=kind,
        unclassified_reason=reason,
    )


def _now() -> str:
    """UTC to the second, in the same shape as the harvest timestamps."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _still_valid(row: sqlite3.Row, digest: str) -> bool:
    """Whether a stored row still answers for this advert.

    Three keys, and one exception to them. The content hash and the prompt wording
    both decide the answer, so a change in either means the row describes a question
    that is no longer being asked. The model does too — but only where a model was
    used: a verdict reached without one (an advert with nothing to classify) has no
    model in it to invalidate, and re-reading its row under a new model would only
    rewrite the same sentence.
    """
    if row["content_hash"] != digest:
        return False
    if not row["model"]:
        return True
    return (
        row["model"] == ai_service.MODEL_NAME
        and row["prompt_version"] == prompt_version()
    )


def _cached(listing_id: str, digest: str) -> Optional[Dict[str, Any]]:
    """The stored verdict for this advert, or None when there is nothing usable."""
    if not listing_id:
        return None
    row = _rows([listing_id]).get(listing_id)
    if row is None or not _still_valid(row, digest):
        return None
    return json.loads(row["classification_json"])


def _rows(ids: List[str]) -> Dict[str, sqlite3.Row]:
    """The stored rows for these ids, in chunks SQLite can hold in one statement."""
    rows: Dict[str, sqlite3.Row] = {}
    if not ids:
        return rows
    conn = get_connection()
    try:
        for start in range(0, len(ids), _ID_CHUNK):
            chunk = ids[start:start + _ID_CHUNK]
            placeholders = ", ".join("?" for _ in chunk)
            cursor = conn.execute(
                "SELECT * FROM listing_classifications "
                f"WHERE listing_id IN ({placeholders});",
                chunk,
            )
            rows.update({row["listing_id"]: row for row in cursor.fetchall()})
    finally:
        conn.close()
    return rows


def _store(record: ListingClassification, digest: str) -> None:
    """Writes a verdict down, replacing whatever was stored for the listing before.

    One row per listing, overwritten in place: a listing has one current reading of
    one advert, and keeping its history would only make "which verdict is in force"
    a question. A payload with no id is not stored at all — there is nothing to look
    it up by, so it is classified for the caller in hand and no further.
    """
    if not record.listing_id:
        log.warning("classified a listing without an id; it will not be cached")
        return
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO listing_classifications (
                    listing_id, content_hash, model, prompt_version, primary_category,
                    canonical_role, confidence, classification_json, classified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(listing_id) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    model = excluded.model,
                    prompt_version = excluded.prompt_version,
                    primary_category = excluded.primary_category,
                    canonical_role = excluded.canonical_role,
                    confidence = excluded.confidence,
                    classification_json = excluded.classification_json,
                    classified_at = excluded.classified_at;
                """,
                (
                    record.listing_id,
                    digest,
                    record.model,
                    record.prompt_version,
                    record.primary_category,
                    record.canonical_role,
                    record.classification_confidence,
                    record.model_dump_json(),
                    record.classified_at,
                ),
            )
    finally:
        conn.close()
