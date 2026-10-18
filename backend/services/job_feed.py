"""
Live job postings, collected from public job-board APIs.

The curated role catalog (`data/roles.json`) answers *what is this career like?*
This module answers *what is actually open right now?* — it pulls from public,
documented JSON APIs, normalises every board's shape into one posting record, and
strips the HTML so the text can be embedded and searched.

| Board | Endpoint | Paging | Terms |
|---|---|---|---|
| Adzuna | `api.adzuna.com/v1/api/jobs/{country}/search/{page}` | `?results_per_page=` (max 50), page in the path | keyed (`ADZUNA_APP_ID`/`ADZUNA_APP_KEY`); publishing listings permitted, but every displayed advert must be labelled "Adzuna" and linked to the local site, and `redirect_url` is the link to use |
| Himalayas | `himalayas.app/jobs/api` | `?limit=` (max 20) + `?offset=` | public feed |
| Arbeitnow | `arbeitnow.com/api/job-board-api` | `?page=` (300/page) | asks callers not to abuse it and to link back |

Every one of those asks is respected: a descriptive `User-Agent`, a short pause
between pages, a documented hard cap on pages per source, and every posting keeps
its board name, its own URL and the board's own id for it (`source_job_id`), so
the original listing stays one click away and a row can always be traced back to
what published it.

**Adzuna leads** because it is the only board here that publishes *into India*:
`in` is one of the markets its API documents, and it aggregates Indian boards and
employers rather than being a single one. That is what makes an India-first feed
possible — the depth of a remote-first global board is no longer the only lever on
whether the home market is in the feed at all. Its terms bound the harvest,
though: the free tier is 25 hits a minute and 250 a day, so `ADZUNA_QUERIES` is a
bounded plan (see the constant) rather than "read everything Adzuna has".

The boards that came first are kept as the *supplementary* sources they have
become: Himalayas is remote-first and global, Arbeitnow is German, and neither
takes a country, a city or even a keyword — asking Himalayas for `country=India`
returns its ordinary newest-first feed, unchanged. Neither carries much of the
home market, which is the gap Adzuna fills, and `MAX_PAGES` now sizes them to
their supplementary role rather than stretching one of them toward India.

What is collected is written to an artifact that records **when it was pulled** and
**what each board did** (`save`/`load_artifact`), because postings age and a board
is not always readable: a board goes on serving a listing after the job is filled,
nothing in the posting itself says when we looked, and only the harvest hears that
Adzuna was never configured. Both travel with the data into the index — the stamp
so the API can tell a candidate how old the feed is, the board record so a feed
missing a provider can say which one and why instead of just being short.

Network access is confined to `_get_json`, so the whole module can be tested
offline against captured fixtures. Normalisation, de-duplication and document
building are pure functions. A board that refuses the request is reported by that
one function, and it names the endpoint with the query — on a keyed board, the
credential — left out (`without_credentials`), because the report travels into the
index and on to the API rather than staying in a log.
"""

import html
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

import httpx

from app_logging import get_logger

log = get_logger("careercompass.jobs")

SOURCE_ADZUNA = "adzuna"
SOURCE_HIMALAYAS = "himalayas"
SOURCE_ARBEITNOW = "arbeitnow"

#: The order a harvest reads the boards in. Adzuna is first because the collection
#: is spent source by source (`collect`): the India-first board gets its pages
#: before the supplementary ones are topped up, rather than being the one left
#: short when the cap is reached.
SOURCES: Sequence[str] = (SOURCE_ADZUNA, SOURCE_HIMALAYAS, SOURCE_ARBEITNOW)

HIMALAYAS_URL = "https://himalayas.app/jobs/api"
ARBEITNOW_URL = "https://arbeitnow.com/api/job-board-api"
ADZUNA_API = "https://api.adzuna.com/v1/api"

# Request manners, and the per-source page ceiling that keeps us a polite guest.
USER_AGENT = "CareerCompass/1.0 (educational career-guidance project)"
REQUEST_TIMEOUT = 25.0
PAUSE_SECONDS = 0.4
PAGE_SIZE = {SOURCE_ADZUNA: 50, SOURCE_HIMALAYAS: 20, SOURCE_ARBEITNOW: 300}

#: How many times one request is attempted before its board is given up on, and how
#: long to wait between attempts. A board is read over dozens of requests — Adzuna's
#: plan alone is twenty-one pages — so a transient failure somewhere in the run is
#: the ordinary case, not the exceptional one: a resolver that blinks, a connection
#: that is dropped, a board that answers 503 for a moment. Without a retry a single
#: such failure discards every page already read from that board, which is how a
#: twenty-one page harvest of the home market comes back with nothing in it. A
#: *refusal* is not retried — a 400 means the request is wrong, and asking the same
#: question again would only spend another hit of a small daily allowance.
REQUEST_ATTEMPTS = 3
RETRY_PAUSE_SECONDS = 1.5

#: Pages per *feed* — one feed per board for the two unkeyed boards (Adzuna runs
#: one feed per market query, each sized in `ADZUNA_QUERIES`). These two are sized
#: to what they now are: the supplementary sources, and what an "abroad" answer
#: falls back on. Himalayas was read fifty pages deep because India is about one
#: listing in thirty of its remote-first global feed and depth was the only lever
#: this app had on the home market — Adzuna supplies that market directly now, so
#: ten pages keep a global remote sample without the thousand listings that made
#: the feed lean Europe and the US. Arbeitnow is a German board paging 300 at a
#: time, and one page is a sample of it rather than a re-export of it.
MAX_PAGES = {SOURCE_HIMALAYAS: 10, SOURCE_ARBEITNOW: 1}

#: The Adzuna market the harvest reads, as its API's own country code. India:
#: this feed is India-first and Adzuna is the one board here that publishes into it.
ADZUNA_DEFAULT_COUNTRY = "in"

#: The Adzuna sector the queries are narrowed to, by the tag Adzuna itself uses
#: for IT vacancies (`Category.tag` — "the string which should be passed to the
#: search endpoint"). Set `ADZUNA_CATEGORY=` to read every sector, which is the
#: honest thing to do if a market ever answers nothing at all: a tag it does not
#: carry would quietly harvest zero postings and look like an outage.
ADZUNA_DEFAULT_CATEGORY = "it-jobs"

#: How far back an Adzuna query looks. Its own default is unbounded, and the
#: boards rotate listings, so a month is enough for a posting to still be worth a
#: candidate's click without spending the daily hit budget on rows the other
#: sources already covered.
ADZUNA_MAX_DAYS_OLD = 30

#: Every Adzuna query a harvest makes, in order, each with the pages it is worth.
#
#: Paging is what buys coverage — Adzuna has no "everything new" feed — and the
#: market is deliberately read twice over: India-wide, and then city by city,
#: because the newest postings nationally are not the newest in Bangalore, and a
#: hub query is the only way to see what a city itself holds. `what=remote` is the
#: closest the API comes to the work-arrangement filter it does not publish.
#:
#: Twenty-five pages of fifty is 1,250 adverts, much the largest share of the feed:
#: India is meant to lead it rather than be a corner of it. Depth stops at
#: twenty-five for a reason that is *not* the daily allowance — the free tier also
#: allows twenty-five hits a *minute*, and pages go out back to back, so a deeper
#: plan rate-limits itself part-way through and loses the pages it has not read
#: yet. Twenty-five pages is 25 of the 250 daily hits, which still leaves room for
#: several re-runs after a failure; `test_the_adzuna_plan_stays_inside_the_free_tier`
#: holds both allowances to that.
ADZUNA_QUERIES: Sequence[Dict[str, Any]] = (
    {"label": "India", "params": {}, "pages": 12},
    {"label": "Bangalore", "params": {"where": "Bangalore"}, "pages": 2},
    {"label": "Hyderabad", "params": {"where": "Hyderabad"}, "pages": 2},
    {"label": "Pune", "params": {"where": "Pune"}, "pages": 2},
    {"label": "Mumbai", "params": {"where": "Mumbai"}, "pages": 2},
    {"label": "Delhi", "params": {"where": "Delhi"}, "pages": 2},
    {"label": "Chennai", "params": {"where": "Chennai"}, "pages": 2},
    {"label": "Remote", "params": {"what": "remote"}, "pages": 1},
)

#: What Adzuna's market codes mean in money. The API states a salary "in the local
#: currency" and then never says which currency that is (`Job.salary_min`), so the
#: market the query named is the only thing that can answer it. A code outside this
#: table leaves the currency blank — a bare number is honest, a guessed currency
#: symbol is not.
ADZUNA_CURRENCIES = {
    "in": "INR",
    "gb": "GBP",
    "us": "USD",
    "ca": "CAD",
    "au": "AUD",
    "nz": "NZD",
    "sg": "SGD",
    "za": "ZAR",
    "br": "BRL",
    "mx": "MXN",
    "at": "EUR",
    "be": "EUR",
    "de": "EUR",
    "es": "EUR",
    "fr": "EUR",
    "it": "EUR",
    "nl": "EUR",
    "ch": "CHF",
    "pl": "PLN",
}

#: Words that make an advert remote *when the board publishes no remote flag*.
#: Adzuna's own site offers a remote filter; its API does not, so this is a
#: reading of the advert's text and is labelled as one (`JobPosting.remote` on a
#: card says "derived"). Whole words only, so "remotely monitored" is not enough
#: on its own — the phrases below are the ones Indian adverts actually use.
REMOTE_WORDS = ("remote", "work from home", "wfh", "telecommute", "work from anywhere")

# How much listing text a card displays, and how much is embedded. The embedded
# text is also kept in the payload, because the API answers its keyword condition
# from the payload and a card's 320-character excerpt is not what was ranked on.
PAYLOAD_EXCERPT = 320
DOCUMENT_EXCERPT = 700

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_KEY_RE = re.compile(r"[^a-z0-9]+")
_WORD_RE = re.compile(r"[^a-z0-9]+")


# ── Adzuna's terms ────────────────────────────────────────────────────────────
class SourceUnavailable(RuntimeError):
    """A board the harvest asked for could not be read, and why.

    Raised rather than quietly returning nothing, because "this board is not
    configured" and "this board had nothing new" are different facts and the
    ingest reports them differently — the first is a deployment problem a reader
    can act on, the second is just a quiet day. `collect` catches it like any
    other failure, so the boards that *are* configured still load.
    """


def adzuna_settings() -> Dict[str, str]:
    """Adzuna's credentials and market, read when a harvest runs.

    Read here rather than at import time so a test, or a host that exports the
    variables after the process started, is respected — and so an unset key
    degrades one board of the harvest instead of breaking the app the way a
    module-level requirement would. That is the same shape as `GEMINI_API_KEY`:
    the feature is off until someone turns it on, and the response says so.
    """
    return {
        "app_id": os.environ.get("ADZUNA_APP_ID", "").strip(),
        "app_key": os.environ.get("ADZUNA_APP_KEY", "").strip(),
        "country": os.environ.get("ADZUNA_COUNTRY", "").strip() or ADZUNA_DEFAULT_COUNTRY,
        # `.get` with a default, not `or`: unset means "the IT market by default",
        # while an explicitly empty value means "every sector".
        "category": os.environ.get("ADZUNA_CATEGORY", ADZUNA_DEFAULT_CATEGORY).strip(),
    }


def adzuna_unavailable() -> str:
    """Why Adzuna cannot be read, or "" when it can.

    The wording is what a candidate ends up reading in the Jobs page's provider
    notice, so it names the variables to set and where to get them rather than
    saying "unavailable" and leaving it there.
    """
    settings = adzuna_settings()
    missing = [
        name
        for name, key in (("ADZUNA_APP_ID", "app_id"), ("ADZUNA_APP_KEY", "app_key"))
        if not settings[key]
    ]
    if missing:
        return (
            f"Adzuna is not configured on this server: {' and '.join(missing)} must "
            "be set in the backend environment (a free app id and key come from "
            "https://developer.adzuna.com/signup). The other boards still load."
        )
    return ""


#: A "credential" shorter than this is a misconfiguration rather than a secret, and
#: replacing it would mangle the message while hiding nothing.
MIN_SECRET_LENGTH = 6


def without_credentials(text: str) -> str:
    """`text` with any credential this server holds taken out of it.

    Adzuna's app id and key travel in the query string, and an HTTP failure quotes
    the whole URL, so a rejected key can otherwise be reproduced verbatim by
    whatever reports the rejection. That is not a private channel: the harvest
    records the message, the ingest writes it into the artifact and the index
    sidecar, and `/jobs/search` serves it to anyone who asks.

    Redacting by *value* rather than by shape is what makes the guarantee
    independent of how a particular HTTP library words its errors, and it is
    applied at both ends — where the message is made (`_request_failure`) and where
    it is served (`job_service.source_status`) — because an index written before any
    of this existed is still an index the API can be asked about.
    """
    settings = adzuna_settings()
    for secret in (settings["app_key"], settings["app_id"]):
        if len(secret) >= MIN_SECRET_LENGTH:
            text = text.replace(secret, "[redacted]")
    return text


# ── HTTP ──────────────────────────────────────────────────────────────────────
def _pause(seconds: float = PAUSE_SECONDS) -> None:
    """A deliberate pause between page requests (patched out in tests)."""
    if seconds > 0:
        time.sleep(seconds)


def _request_failure(error: httpx.HTTPError, url: str) -> str:
    """Why a request failed, said in a form safe to write down and to serve.

    The endpoint is named without its query, because the query is where the
    credentials ride: "401 Unauthorized from
    https://api.adzuna.com/v1/api/jobs/in/search/1" tells a reader everything they
    can act on and nothing they should not have. The credentials are scrubbed out of
    whatever is left as well, so the guarantee holds even if some future error
    spells a secret somewhere other than the query.
    """
    if isinstance(error, httpx.HTTPStatusError):
        detail = f"{error.response.status_code} {error.response.reason_phrase}".strip()
    else:
        detail = f"{type(error).__name__}: {error}".strip()
    return without_credentials(f"{detail} from {url.split('?', 1)[0]}")


def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fetches one JSON document, retrying a transient failure.

    The only function here that touches the network. A dropped connection, a
    timeout or a board answering 5xx is attempted again (`REQUEST_ATTEMPTS`) before
    the board is called unreadable, because a failure part-way through a paged read
    otherwise discards every page already fetched from it. A refusal is *not*
    retried: a 400 says the request itself is wrong, and repeating it would spend
    another hit of a small daily allowance to be told so again.

    Every failure leaves here as a `SourceUnavailable` instead of as the library's
    own error, for two reasons. Its message names what refused and where — with the
    query, and so the credentials, left out (see `without_credentials`) — and the
    original error is not chained into the traceback, where its own message, which
    is the whole URL, would still be printed.
    """
    failure: Optional[httpx.HTTPError] = None
    for attempt in range(REQUEST_ATTEMPTS):
        try:
            response = httpx.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            failure = error
            if error.response.status_code < 500:
                break
        except httpx.TransportError as error:
            failure = error
        if attempt + 1 < REQUEST_ATTEMPTS:
            _pause(RETRY_PAUSE_SECONDS)
    raise SourceUnavailable(_request_failure(failure, url)) from None


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


def _absolute_date(value: Any) -> str:
    """A publication date as `YYYY-MM-DD`, from an epoch or an ISO 8601 stamp.

    The boards disagree about how to write a date: Himalayas and Arbeitnow both
    send epoch seconds, while Adzuna sends an ISO 8601 date *time* string
    (`Ad.created`, "The date the advertisement was placed"). Both are accepted
    here so the posting record has one kind of date in it either way.
    """
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return _iso_date(value)


def published_epoch(published: str) -> Optional[int]:
    """A publication date as a UTC epoch, for the "posted within" range filter.

    Not a fact about the advert — it is the same fact as `published`, in the form
    a range condition can compare — which is why the payload carries it and the
    posting record does not. Midnight UTC on the day `published` names, so a
    posting is never *newer* than its own date; an absent or unreadable date
    answers None, and a posting with no date is then excluded by any "posted
    within" filter rather than surviving one on a technicality.
    """
    text = str(published or "").strip()
    if not text:
        return None
    try:
        moment = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return int(moment.timestamp())


def _mentions_any(text: str, phrases: Sequence[str]) -> bool:
    """Whether `text` says one of these phrases, as whole words.

    Used for the one thing a board's payload does not state (see `REMOTE_WORDS`),
    so it tokenises the way the store's own filter does rather than searching for
    substrings — "wfh" has to be a word, not the middle of one.
    """
    words = {word for word in _WORD_RE.split(str(text).casefold()) if word}
    for phrase in phrases:
        needle = [word for word in _WORD_RE.split(phrase.casefold()) if word]
        if needle and all(word in words for word in needle):
            return True
    return False


def _dedupe_key(posting: Dict[str, Any]) -> str:
    """Board-independent key: the same opening *in the same place* is the same one.

    Title and company alone are not enough. A company advertising one title twice
    — "Software Engineer" in Pune and again in Hyderabad — is advertising two
    vacancies, and collapsing them loses one for good: only the surviving row is
    ever indexed, so the posting the other board carried cannot come back. The
    place is therefore part of the key, and rows collapse only when they agree on
    all three.

    The cost is the mirror image: the same opening written up by two boards in two
    different places ("Bangalore, Karnataka, India" against "India, Singapore")
    stays as two rows. That is the direction to err in — a duplicate is visible
    and a card names the board it came from, whereas a merged-away vacancy is
    simply gone.
    """
    title = _KEY_RE.sub(" ", str(posting.get("title") or "").lower()).strip()
    company = _KEY_RE.sub(" ", str(posting.get("company") or "").lower()).strip()
    place = _KEY_RE.sub(" ", str(posting.get("location") or "").lower()).strip()
    return f"{title}|{company}|{place}"


# ── Normalisation ─────────────────────────────────────────────────────────────
def _base_posting(source: str) -> Dict[str, Any]:
    return {
        "id": "",
        "source": source,
        #: The board's own identifier for the listing, kept beside the namespaced
        #: `id` we key on. It is what a card's board would recognise, and it is the
        #: only way back to a row if the boards ever need to be reconciled.
        "source_job_id": "",
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
            "source_job_id": _text(raw.get("guid")) or url,
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
            "published": _absolute_date(raw.get("pubDate")),
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
            "source_job_id": _text(raw.get("slug")) or url,
            "title": title,
            "company": _text(raw.get("company_name")),
            "location": location or ("Remote" if raw.get("remote") else ""),
            "remote": bool(raw.get("remote")),
            "employment_type": ", ".join(_string_list(raw.get("job_types"))),
            "categories": _string_list(raw.get("tags")),
            "tags": _string_list(raw.get("tags")),
            "published": _absolute_date(raw.get("created_at")),
            "url": url,
            "description": _text(raw.get("description")),
        }
    )
    return posting


def _adzuna_place(location: Any) -> str:
    """Where an Adzuna advert is, most specific first ("Mumbai, Maharashtra, India").

    Adzuna names a place as an `area` list, "each refining the location more than
    the previous" — country first — where the other boards write one free-text
    string. It is turned round and joined, because the Jobs page reads places out
    of this field and splits it on commas, and the country has to be a segment of
    its own: otherwise an advert naming only "Mumbai, Maharashtra" would not match
    a search for India, and the one board that actually covers the home market
    would count for nothing in it.

    `display_name` is the fallback for an advert with no `area` at all, not an
    addition to it — it repeats the city and the state, and a location reading
    "Mumbai, Maharashtra, India, Mumbai, Maharashtra" is a worse answer than a
    shorter one.
    """
    if not isinstance(location, dict):
        return ""
    area = _string_list(location.get("area"))
    return ", ".join(reversed(area)) or _text(location.get("display_name"))


def _adzuna_employment(raw: Dict[str, Any]) -> str:
    """How an advert hires, from the two fields that describe it.

    `contract_time` ("full_time" or "part_time") and `contract_type` ("permanent"
    or "contract") are separate answers to separate questions, so both are kept a
    permanent full-time role reads "full time, permanent" and the Jobs page's
    employment filter can ask for either half of that. Adzuna is the only board
    here that publishes either one.
    """
    parts = [
        _text(raw.get(field)).replace("_", " ")
        for field in ("contract_time", "contract_type")
    ]
    return ", ".join(dict.fromkeys(part for part in parts if part))


def normalise_adzuna(raw: Dict[str, Any], currency: str = "") -> Optional[Dict[str, Any]]:
    """One Adzuna advert -> the shared posting shape (None when unusable).

    Adzuna's shape is the least like the other boards': the location is a nested
    `area` list rather than a string, the employment wording is two separate
    fields, the description is truncated to 500 characters by Adzuna itself, and
    the pay carries no currency — a market code is passed in as `currency` by the
    feed that fetched it (see `ADZUNA_CURRENCIES`).

    Two of Adzuna's own facts decide fields outright:

    * `redirect_url` is the URL, not a convenience. Its field description says
      using it "to send users to the advertiser's site" is required to comply with
      Adzuna's terms, so it is what the posting keeps.
    * `salary_is_predicted` marks a figure Jobsworth *estimated* rather than one
      the advertiser stated. An estimate rendered as "INR 900000" is
      indistinguishable from a disclosed salary, so it is dropped instead of
      dressed up: this app already publishes its own modelled bands, and a
      candidate is owed the difference between a number someone offered and a
      number a model guessed.
    """
    title = _text(raw.get("title"))
    url = _text(raw.get("redirect_url"))
    if not (title and url):
        return None
    identifier = _text(raw.get("id")) or url
    company = raw.get("company") if isinstance(raw.get("company"), dict) else {}
    category = raw.get("category") if isinstance(raw.get("category"), dict) else {}
    label = _text(category.get("label"))
    predicted = str(raw.get("salary_is_predicted", "")).strip().lower() in ("1", "true", "yes")
    salary_min = None if predicted else _as_int(raw.get("salary_min"))
    salary_max = None if predicted else _as_int(raw.get("salary_max"))

    posting = _base_posting(SOURCE_ADZUNA)
    posting.update(
        {
            "id": f"{SOURCE_ADZUNA}:{identifier}",
            "source_job_id": identifier,
            "title": title,
            "company": _text(company.get("display_name")),
            "location": _adzuna_place(raw.get("location")),
            # Adzuna publishes no remote flag, so this one field is read out of
            # the advert's own words (see REMOTE_WORDS) and the page says so.
            "remote": _mentions_any(f"{title} {raw.get('description') or ''}", REMOTE_WORDS),
            "employment_type": _adzuna_employment(raw),
            "categories": [label] if label else [],
            "salary_min": salary_min,
            "salary_max": salary_max,
            "salary_currency": currency if (salary_min or salary_max) else "",
            # Adzuna states no pay period, so none is asserted here: the figures
            # are quoted as given rather than labelled "annual" on the API's behalf.
            "salary_period": "",
            "published": _absolute_date(raw.get("created")),
            "url": url,
            "description": _text(raw.get("description")),
        }
    )
    return posting


NORMALISERS: Dict[str, Callable[..., Optional[Dict[str, Any]]]] = {
    SOURCE_ADZUNA: normalise_adzuna,
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
    """The stored, displayable record: everything but the long description.

    `excerpt` is what a card shows; `search_text` is the text that was embedded,
    kept so the API can answer a keyword question against the same words the index
    ranked on instead of against the first 320 characters of them. A display field
    and a search field, deliberately separate.

    `published_ts` is the same publication date as `published`, as an epoch, for
    the one filter that has to compare it rather than show it ("posted within a
    week"). Added here rather than carried from normalisation because it is a
    rendering of a field every posting already has — and left out entirely when
    the board dated the posting not at all, so an undated advert is excluded by a
    date filter instead of sneaking inside one.
    """
    payload = {key: value for key, value in posting.items() if key != "description"}
    payload["excerpt"] = _truncate(str(posting.get("description") or ""), PAYLOAD_EXCERPT)
    payload["salary_text"] = salary_text(posting)
    payload["search_text"] = posting_document(posting)
    stamp = published_epoch(posting.get("published") or "")
    if stamp is not None:
        payload["published_ts"] = stamp
    return payload


def row_for(posting: Dict[str, Any]) -> Dict[str, Any]:
    """The `(id, document, payload)` triple `vector_store.upsert_records` wants."""
    return {
        "record_id": str(posting.get("id") or posting.get("url") or ""),
        "document": posting_document(posting),
        "payload": posting_payload(posting),
    }


# ── Fetching ──────────────────────────────────────────────────────────────────
class Feed(NamedTuple):
    """One paged feed of one board: how to ask for page N, and what to make of it.

    A board is read through one or more of these. Himalayas and Arbeitnow are one
    feed each; Adzuna is one feed per market query, because it has no single
    "everything new" feed to walk. Keeping the normaliser on the *feed* rather than
    looking it up per board is what lets Adzuna's pages carry the currency of the
    market they came from: the API states a salary in "the local currency" and then
    never says which it is.
    """

    label: str
    normalise: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]
    #: Page index (from 0) -> the URL and query to ask for it with.
    page_request: Callable[[int], Tuple[str, Dict[str, Any]]]
    items_key: str
    page_size: int
    pages: int


def _adzuna_feeds() -> Tuple[Feed, ...]:
    """One feed per market query, or a refusal naming exactly what is missing.

    The plan is `ADZUNA_QUERIES` — a bounded number of pages per market, because
    the free tier's hit budget is small enough that a harvest must be able to run
    more than once a day without running out.
    """
    reason = adzuna_unavailable()
    if reason:
        raise SourceUnavailable(reason)
    settings = adzuna_settings()
    currency = ADZUNA_CURRENCIES.get(settings["country"].lower(), "")
    base: Dict[str, Any] = {
        "app_id": settings["app_id"],
        "app_key": settings["app_key"],
        "results_per_page": PAGE_SIZE[SOURCE_ADZUNA],
        # `sort_by=date` is already newest-first, and no `sort_dir` is sent with it.
        # Adzuna stopped accepting the parameter — every value it documents, and
        # every other spelling, now answers 400 Bad Request — and asking anyway
        # turns the whole board into one that could not be read, for a direction
        # `sort_by=date` already gives.
        "sort_by": "date",
        "max_days_old": ADZUNA_MAX_DAYS_OLD,
        "content-type": "application/json",
    }
    if settings["category"]:
        base["category"] = settings["category"]

    def normalise(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return normalise_adzuna(raw, currency)

    feeds: List[Feed] = []
    for query in ADZUNA_QUERIES:
        url = f"{ADZUNA_API}/jobs/{settings['country']}/search"
        params = {**base, **(query.get("params") or {})}

        def page_request(page: int, url: str = url, params: Dict[str, Any] = params):
            # The page is in the path for this API, not a parameter — which is the
            # other reason a feed owns its own page request rather than the caller.
            return f"{url}/{page + 1}", dict(params)

        feeds.append(
            Feed(
                label=str(query.get("label") or settings["country"]),
                normalise=normalise,
                page_request=page_request,
                items_key="results",
                page_size=PAGE_SIZE[SOURCE_ADZUNA],
                pages=int(query.get("pages") or 1),
            )
        )
    return tuple(feeds)


def _feeds(source: str) -> Tuple[Feed, ...]:
    """Every feed a board is read through, in order.

    The two unkeyed boards are one paged feed apiece, sized from `PAGE_SIZE` and
    `MAX_PAGES` *when this is called* rather than captured at import, so those
    constants stay the one place a board's manners are written.
    """
    if source == SOURCE_ADZUNA:
        return _adzuna_feeds()

    page_size, pages = PAGE_SIZE[source], MAX_PAGES[source]
    if source == SOURCE_HIMALAYAS:
        feed = Feed(
            label=SOURCE_HIMALAYAS,
            normalise=normalise_himalayas,
            page_request=lambda page, size=page_size: (
                HIMALAYAS_URL,
                {"limit": size, "offset": page * size},
            ),
            items_key="jobs",
            page_size=page_size,
            pages=pages,
        )
    else:
        feed = Feed(
            label=SOURCE_ARBEITNOW,
            normalise=normalise_arbeitnow,
            page_request=lambda page: (ARBEITNOW_URL, {"page": page + 1}),
            items_key="data",
            page_size=page_size,
            pages=pages,
        )
    return (feed,)


def fetch_source(source: str, limit: int) -> List[Dict[str, Any]]:
    """Postings from one board, newest-first as the board returns them.

    Each feed is walked until it is exhausted: the board sends no postings, sends
    a short page, or its own page ceiling is reached. A feed that has nothing left
    therefore costs one request and the *next* feed is tried — which is what a city
    query with nothing new should cost, rather than ending the board's turn.
    """
    if source not in NORMALISERS:
        raise ValueError(f"Unknown job source {source!r}; expected one of {list(NORMALISERS)}")

    collected: List[Dict[str, Any]] = []
    for feed in _feeds(source):
        for page in range(feed.pages):
            if len(collected) >= limit:
                break
            url, params = feed.page_request(page)
            payload = _get_json(url, params)
            raw_items = payload.get(feed.items_key) or []
            if not raw_items:
                break
            for raw in raw_items:
                posting = feed.normalise(raw)
                if posting:
                    collected.append(posting)
            if len(raw_items) < feed.page_size:
                break
            _pause()
    log.info("Fetched %d postings from %s", len(collected), source)
    return collected[:limit]


#: How many postings a full harvest is worth. Sized to clear what the three boards'
#: plans produce between them — Adzuna's twenty-five pages of fifty, Himalayas' ten
#: of twenty, Arbeitnow's one of 300, so 1,750 raw rows — with headroom left, because
#: the cap is spent source by source and a cap below the plans would delete the last
#: board's share of the feed for no reason but arithmetic. `scripts.ingest_jobs`
#: defaults its `--limit` to this, so the two never drift apart.
HARVEST_LIMIT = 2100


def collect(
    limit: int = HARVEST_LIMIT,
    sources: Sequence[str] = SOURCES,
    on_progress: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Postings from every requested board, de-duplicated, capped at `limit`.

    A board that cannot be read — Adzuna with no credentials, a board that is down,
    a board that answers with nonsense — is reported through `on_progress` and
    skipped, never raised, so the rest of the harvest is not its hostage. The
    ingest keeps those reports, which is how `/jobs/search` can say *which* provider
    is missing instead of showing a short feed and no reason for it.
    """
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
    postings: List[Dict[str, Any]],
    path: str,
    harvested_at: str = "",
    sources: Optional[Sequence[Dict[str, Any]]] = None,
) -> str:
    """Writes the collected postings, when they were pulled, and what each board did.

    The timestamp is the artifact's own provenance. A board keeps serving a
    listing after the job is filled, so postings age silently — the publication
    dates say when a job was posted, never when we looked at it — and an index
    built from this file inherits whatever date is written here. Passing one in
    keeps `--from-file` honest, because a re-ingest of an old artifact must not
    claim today's date.

    `sources` is what each board contributed to *this* harvest, including the ones
    that could not be read and why. It travels in the file for the same reason the
    date does: an index is only as informative as the harvest behind it, and a
    re-ingest of this file has no network on which to ask a board again. So a
    harvest that records the record keeps its "Adzuna is not configured" on the
    page even when the file, not the boards, is what gets ingested. Omit it and the
    file holds rows alone, which reads back as no record rather than as an
    all-clear.
    """
    artifact: Dict[str, Any] = {
        "harvested_at": harvested_at or harvest_stamp(),
        "postings": list(postings),
    }
    if sources is not None:
        artifact["sources"] = [dict(entry) for entry in sources]
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=1)
    return path


def load_artifact(path: str) -> Dict[str, Any]:
    """The artifact as saved: its stamp, its postings, and each board's record.

    A bare JSON list is accepted as an artifact written before the harvest time
    was recorded: it loads with an empty stamp rather than failing, so a file
    collected by an older version still re-ingests. An artifact from before the
    board record existed — or one a caller wrote without one — loads with no
    `sources`, which the ingest reads as "nothing was recorded" rather than as a
    report that every board was consulted and had nothing.
    """
    with open(path, encoding="utf-8") as handle:
        artifact = json.load(handle)
    if isinstance(artifact, list):
        return {"harvested_at": "", "postings": artifact, "sources": []}
    if not isinstance(artifact, dict):
        return {"harvested_at": "", "postings": [], "sources": []}
    postings = artifact.get("postings")
    recorded = artifact.get("sources")
    return {
        "harvested_at": str(artifact.get("harvested_at") or ""),
        "postings": list(postings) if isinstance(postings, list) else [],
        "sources": (
            [dict(entry) for entry in recorded if isinstance(entry, dict)]
            if isinstance(recorded, list)
            else []
        ),
    }


def load(path: str) -> List[Dict[str, Any]]:
    """Reads a previously collected artifact (see `save`)."""
    return load_artifact(path)["postings"]
