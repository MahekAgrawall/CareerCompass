"""The live job feed, and the `job_role` collection it fills.

The contract these tests pin down:

* normalisation is total — every board's shape lands in one posting record, HTML
  gone, missing fields empty rather than missing;
* the network is confined to one function, which the tests replace, so the suite
  stays hermetic: no test reaches a job board;
* a board being down degrades the harvest instead of failing it;
* `job_role` records the embedding space it was built in and refuses to mix in
  another one, and rebuilding it never touches the curated role index.

Isolation (throwaway database and index) comes from `tests.harness`.
"""
import contextlib
import httpx
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests.harness import IndexBackedTest, client  # noqa: F401  (isolation first)

from scripts import ingest_jobs  # noqa: E402
from services import embeddings, job_feed, job_service, vector_store  # noqa: E402

HIMALAYAS_RAW = {
    "title": "Senior Platform Engineer (Remote)",
    "excerpt": "Run our Kubernetes platform.",
    "companyName": "Nimbus Labs",
    "companySlug": "nimbus-labs",
    "employmentType": "Full Time",
    "minSalary": 90000,
    "maxSalary": 120000,
    "salaryPeriod": "annual",
    "seniority": ["Senior"],
    "currency": "USD",
    "locationRestrictions": ["India", "Singapore"],
    "categories": ["Platform-Engineering", "Kubernetes"],
    "parentCategories": ["Developer"],
    "description": "<p>Run Kubernetes</p><p>&amp; Terraform at scale</p>",
    "pubDate": 1792251534,  # 2026-10-17 UTC
    "applicationLink": "https://himalayas.app/companies/nimbus-labs/jobs/platform-engineer",
    "guid": "https://himalayas.app/companies/nimbus-labs/jobs/platform-engineer",
}

ARBEITNOW_RAW = {
    "slug": "product-designer-99887",
    "company_name": "Bright Studio",
    "title": "Product Designer",
    "description": "&lt;div&gt;&lt;p&gt;Own Figma design systems.&lt;/p&gt;&lt;/div&gt;",
    "remote": True,
    "url": "https://www.arbeitnow.com/jobs/companies/bright-studio/product-designer-99887",
    "tags": ["Design", "Design", "Figma"],
    "job_types": ["full-time"],
    "location": "Berlin",
    "created_at": 1792248917,  # 2026-10-17 UTC
}

#: An Adzuna advert, in the shape its own API documents: the place as an `area`
#: list (country first), the employment as two fields, the date as an ISO 8601
#: string rather than an epoch, and the link as `redirect_url`.
ADZUNA_RAW = {
    "id": "5091887331",
    "title": "Backend Engineer (Python)",
    "description": "Build our payments API in Python. Work from home is available.",
    "created": "2026-10-16T05:31:00Z",
    "redirect_url": "https://www.adzuna.in/land/ad/5091887331",
    "adref": "eyJhbGciOiJIUzI1NiJ9",
    "location": {
        "__CLASS__": "Adzuna::API::Response::Location",
        "area": ["India", "Karnataka", "Bangalore"],
        "display_name": "Bangalore, Karnataka",
    },
    "category": {
        "__CLASS__": "Adzuna::API::Response::Category",
        "tag": "it-jobs",
        "label": "IT Jobs",
    },
    "company": {
        "__CLASS__": "Adzuna::API::Response::Company",
        "display_name": "Nimbus Labs",
        "canonical_name": "nimbus labs",
    },
    "salary_min": 900000,
    "salary_max": 1400000,
    "salary_is_predicted": "0",
    "contract_time": "full_time",
    "contract_type": "permanent",
}


def posting_fixture(identifier, title, company, description, **overrides):
    posting = {
        "id": identifier,
        "source": "arbeitnow",
        "source_job_id": identifier.split(":", 1)[-1],
        "title": title,
        "company": company,
        "location": "Remote",
        "remote": True,
        "employment_type": "full-time",
        "seniority": [],
        "categories": [],
        "tags": [],
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "",
        "salary_period": "",
        "published": "2026-10-01",
        "url": f"https://example.com/{identifier}",
        "description": description,
    }
    posting.update(overrides)
    return posting


PLATFORM = posting_fixture(
    "himalayas:platform", "Senior Platform Engineer", "Nimbus Labs",
    "Run Kubernetes clusters and Terraform deployment pipelines on cloud infrastructure.",
    categories=["Platform-Engineering"],
)
DESIGNER = posting_fixture(
    "himalayas:designer", "Product Designer", "Bright Studio",
    "Run user interviews, usability studies and Figma wireframes for product teams.",
    categories=["Design"],
)


def role_fixture(role_id, title, interests, skills):
    """A minimal role that satisfies `career_service`'s index document."""
    return {
        "id": role_id,
        "title": title,
        "category": "Test",
        "niche_category": "Test",
        "description": f"{title} works on {', '.join(skills)}.",
        "responsibilities": [f"Work with {skill}" for skill in skills],
        "growth_path": [title],
        "skills": {"must_have": list(skills), "good_to_have": [], "can_have": []},
        "matching_interests": list(interests),
        "matching_skills": list(skills),
    }


class NormalisationTests(unittest.TestCase):
    def test_himalayas_posting_is_mapped_completely(self):
        posting = job_feed.normalise_himalayas(HIMALAYAS_RAW)
        self.assertEqual(posting["id"], "himalayas:" + HIMALAYAS_RAW["guid"])
        self.assertEqual(posting["source"], "himalayas")
        self.assertEqual(posting["source_job_id"], HIMALAYAS_RAW["guid"])
        self.assertEqual(posting["title"], "Senior Platform Engineer (Remote)")
        self.assertEqual(posting["company"], "Nimbus Labs")
        self.assertEqual(posting["location"], "India, Singapore")
        self.assertTrue(posting["remote"])
        self.assertEqual(posting["employment_type"], "Full Time")
        self.assertEqual(posting["seniority"], ["Senior"])
        self.assertEqual(posting["salary_min"], 90000)
        self.assertEqual(posting["salary_max"], 120000)
        self.assertEqual(posting["salary_currency"], "USD")
        self.assertEqual(posting["salary_period"], "annual")
        self.assertEqual(posting["published"], "2026-10-17")
        self.assertEqual(posting["url"], HIMALAYAS_RAW["applicationLink"])

    def test_himalayas_description_loses_its_markup(self):
        posting = job_feed.normalise_himalayas(HIMALAYAS_RAW)
        self.assertEqual(posting["description"], "Run Kubernetes & Terraform at scale")
        self.assertNotIn("<", posting["description"])

    def test_arbeitnow_posting_unescapes_then_strips_markup(self):
        """Arbeitnow double-encodes its HTML, so unescaping must come first."""
        posting = job_feed.normalise_arbeitnow(ARBEITNOW_RAW)
        self.assertEqual(posting["id"], "arbeitnow:" + ARBEITNOW_RAW["slug"])
        self.assertEqual(posting["source_job_id"], ARBEITNOW_RAW["slug"])
        self.assertEqual(posting["description"], "Own Figma design systems.")
        self.assertEqual(posting["location"], "Berlin")
        self.assertEqual(posting["employment_type"], "full-time")
        self.assertTrue(posting["remote"])
        self.assertEqual(posting["published"], "2026-10-17")
        self.assertEqual(posting["salary_min"], None)

    def test_arbeitnow_location_falls_back_to_remote(self):
        raw = dict(ARBEITNOW_RAW, location="", remote=True)
        self.assertEqual(job_feed.normalise_arbeitnow(raw)["location"], "Remote")

    # ── Adzuna ────────────────────────────────────────────────────────────────
    def test_adzuna_posting_is_mapped_completely(self):
        posting = job_feed.normalise_adzuna(ADZUNA_RAW, "INR")
        self.assertEqual(posting["id"], "adzuna:" + ADZUNA_RAW["id"])
        self.assertEqual(posting["source"], "adzuna")
        self.assertEqual(posting["source_job_id"], ADZUNA_RAW["id"])
        self.assertEqual(posting["title"], "Backend Engineer (Python)")
        self.assertEqual(posting["company"], "Nimbus Labs")
        self.assertEqual(posting["employment_type"], "full time, permanent")
        self.assertEqual(posting["categories"], ["IT Jobs"])
        self.assertEqual(posting["salary_min"], 900000)
        self.assertEqual(posting["salary_max"], 1400000)
        self.assertEqual(posting["salary_currency"], "INR")
        self.assertEqual(posting["published"], "2026-10-16")
        self.assertEqual(posting["url"], ADZUNA_RAW["redirect_url"])
        # Adzuna publishes no remote flag and no experience level, so a posting
        # carries whichever of them its own words and fields support.
        self.assertTrue(posting["remote"])
        self.assertEqual(posting["seniority"], [])

    def test_adzuna_place_names_the_country_so_india_can_be_searched(self):
        """The `area` list arrives country-first; it leaves most-specific-first.

        The Jobs page reads places out of `location` by splitting it on commas, and
        the location filter requires every word it is handed — so a posting named
        "Bangalore, Karnataka" alone would not answer a search for India, and the
        one board that covers the home market would count for nothing in it.
        """
        posting = job_feed.normalise_adzuna(ADZUNA_RAW, "INR")
        self.assertEqual(posting["location"], "Bangalore, Karnataka, India")
        self.assertEqual(job_feed.normalise_adzuna(
            dict(ADZUNA_RAW, location={"display_name": "Mumbai, Maharashtra"}), "INR"
        )["location"], "Mumbai, Maharashtra")

    def test_adzuna_employment_keeps_both_halves_of_the_answer(self):
        """`contract_time` and `contract_type` answer different questions."""
        part = job_feed.normalise_adzuna(
            dict(ADZUNA_RAW, contract_time="part_time", contract_type="contract"), "INR"
        )
        self.assertEqual(part["employment_type"], "part time, contract")
        bare = job_feed.normalise_adzuna(
            dict(ADZUNA_RAW, contract_time="", contract_type=""), "INR"
        )
        self.assertEqual(bare["employment_type"], "")

    def test_adzuna_remote_is_read_from_the_adverts_own_words(self):
        """Adzuna's API publishes no remote flag, so this one field is derived.

        The feed's own `what=remote` query can only find adverts that *say*
        something remote, so the flag has to agree with it — precisely enough that
        a candidate filtering on remote gets those adverts and not the rest.
        """
        onsite = job_feed.normalise_adzuna(
            dict(ADZUNA_RAW, description="Maintain the internal billing service."), "INR"
        )
        self.assertFalse(onsite["remote"])
        self.assertTrue(
            job_feed.normalise_adzuna(
                dict(ADZUNA_RAW, description="This is a work from home position."), "INR"
            )["remote"]
        )
        # Whole words: a posting mentioning the adverb is not a remote posting.
        self.assertFalse(
            job_feed.normalise_adzuna(
                dict(ADZUNA_RAW, title="Engineer", description="The fleet is remotely managed."),
                "INR",
            )["remote"]
        )

    def test_adzuna_estimated_salaries_are_not_shown_as_disclosed_ones(self):
        """`salary_is_predicted` marks a Jobsworth estimate, not an offer.

        Rendered as "INR 900000" an estimate is indistinguishable from a figure the
        advertiser stated, and this app already publishes its own modelled bands —
        so a predicted number is dropped rather than presented as a disclosure.
        """
        predicted = job_feed.normalise_adzuna(
            dict(ADZUNA_RAW, salary_is_predicted="1"), "INR"
        )
        self.assertIsNone(predicted["salary_min"])
        self.assertIsNone(predicted["salary_max"])
        self.assertEqual(predicted["salary_currency"], "")
        self.assertEqual(job_feed.salary_text(predicted), "")

    def test_adzuna_currency_comes_from_the_market_that_was_queried(self):
        """The API states a salary "in the local currency" and never says which."""
        self.assertEqual(job_feed.normalise_adzuna(ADZUNA_RAW, "INR")["salary_currency"], "INR")
        self.assertEqual(job_feed.normalise_adzuna(ADZUNA_RAW, "")["salary_currency"], "")
        self.assertEqual(job_feed.ADZUNA_CURRENCIES["in"], "INR")

    def test_adzuna_posting_without_a_title_or_link_is_dropped(self):
        self.assertIsNone(job_feed.normalise_adzuna(dict(ADZUNA_RAW, title=""), "INR"))
        self.assertIsNone(
            job_feed.normalise_adzuna(dict(ADZUNA_RAW, redirect_url=""), "INR")
        )

    def test_a_description_never_reaches_the_payload_it_is_excerpted_into(self):
        payload = job_feed.posting_payload(job_feed.normalise_adzuna(ADZUNA_RAW, "INR"))
        self.assertNotIn("description", payload)
        self.assertIn("Python", payload["excerpt"])

    def test_every_board_dates_a_posting_the_same_way(self):
        """`_absolute_date` reads Adzuna's ISO string and the others' epochs."""
        self.assertEqual(job_feed._absolute_date("2026-10-16T05:31:00Z"), "2026-10-16")
        self.assertEqual(job_feed._absolute_date("2026-10-16"), "2026-10-16")
        self.assertEqual(job_feed._absolute_date(1792248917), "2026-10-17")
        self.assertEqual(job_feed._absolute_date("not a date"), "")

    def test_a_posting_carries_its_date_in_a_form_a_range_can_compare(self):
        """`published_ts` is `published` as an epoch, for the "posted within" filter."""
        payload = job_feed.posting_payload(
            posting_fixture("a", "A", "C", "", published="2026-10-01")
        )
        self.assertEqual(payload["published_ts"], job_feed.published_epoch("2026-10-01"))
        self.assertEqual(payload["published"], "2026-10-01")

    def test_an_undated_posting_has_no_date_to_filter_on(self):
        """Not zero: absent, so a "posted within" filter cannot let it through."""
        payload = job_feed.posting_payload(posting_fixture("a", "A", "C", "", published=""))
        self.assertNotIn("published_ts", payload)
        self.assertIsNone(job_feed.published_epoch(""))
        self.assertIsNone(job_feed.published_epoch("yesterday"))

    def test_a_posting_without_a_title_or_link_is_dropped(self):
        self.assertIsNone(job_feed.normalise_himalayas({"title": "", "guid": ""}))
        self.assertIsNone(job_feed.normalise_arbeitnow({"title": "Designer", "url": ""}))

    def test_tags_are_deduplicated_and_cleaned(self):
        posting = job_feed.normalise_arbeitnow(ARBEITNOW_RAW)
        self.assertEqual(posting["tags"], ["Design", "Figma"])

    def test_salary_text_describes_what_is_known(self):
        both = posting_fixture("a", "A", "C", "", salary_min=90000, salary_max=120000,
                               salary_currency="USD", salary_period="annual")
        one = posting_fixture("b", "B", "C", "", salary_min=50000, salary_currency="EUR")
        none = posting_fixture("c", "C", "C", "")
        self.assertEqual(job_feed.salary_text(both), "USD 90000-120000 / annual")
        self.assertEqual(job_feed.salary_text(one), "EUR 50000")
        self.assertEqual(job_feed.salary_text(none), "")

    def test_document_carries_the_signals_a_candidate_searches_on(self):
        document = job_feed.posting_document(job_feed.normalise_himalayas(HIMALAYAS_RAW))
        self.assertIn("Senior Platform Engineer", document)
        self.assertIn("Nimbus Labs", document)
        self.assertIn("Kubernetes", document)
        self.assertIn("Remote", document)
        self.assertIn("USD 90000-120000 / annual", document)

    def test_document_omits_sections_it_has_no_data_for(self):
        bare = posting_fixture("x", "Solo Title", "", "", location="", remote=False,
                               employment_type="")
        self.assertEqual(job_feed.posting_document(bare), "Solo Title")

    def test_document_is_bounded_so_one_listing_cannot_dominate(self):
        posting = posting_fixture("long", "Long", "Co", "word " * 5000)
        self.assertLessEqual(len(job_feed.posting_document(posting)), job_feed.DOCUMENT_EXCERPT + 200)

    def test_payload_keeps_a_readable_excerpt_not_the_whole_listing(self):
        posting = posting_fixture("p", "P", "Co", "sentence " * 500)
        payload = job_feed.posting_payload(posting)
        self.assertNotIn("description", payload)
        self.assertLessEqual(len(payload["excerpt"]), job_feed.PAYLOAD_EXCERPT)
        self.assertEqual(payload["title"], "P")

    def test_payload_keeps_the_text_it_embedded_for_keyword_matching(self):
        """The API judges a keyword against the payload, so it must hold what the
        index actually ranked on — the card's 320-character excerpt does not."""
        posting = posting_fixture("p", "P", "Co", "word " * 500)
        payload = job_feed.posting_payload(posting)
        self.assertEqual(payload["search_text"], job_feed.posting_document(posting))
        self.assertGreater(len(payload["search_text"]), len(payload["excerpt"]))


class DedupeTests(unittest.TestCase):
    def test_the_same_opening_on_two_boards_collapses(self):
        first = posting_fixture("a", "Senior Backend Engineer", "Acme", "one")
        second = posting_fixture("b", "senior backend engineer", "ACME", "two")
        self.assertEqual(len(job_feed.dedupe([first, second])), 1)
        self.assertEqual(job_feed.dedupe([first, second])[0]["id"], "a")

    def test_punctuation_does_not_hide_a_duplicate(self):
        first = posting_fixture("a", "Backend Engineer (m/f/d)", "Acme", "one")
        second = posting_fixture("b", "backend engineer m f d", "Acme", "two")
        self.assertEqual(len(job_feed.dedupe([first, second])), 1)

    def test_genuinely_different_openings_survive(self):
        same_title = posting_fixture("a", "Backend Engineer", "Acme", "one")
        other_company = posting_fixture("b", "Backend Engineer", "Globex", "two")
        other_role = posting_fixture("c", "Frontend Engineer", "Acme", "three")
        self.assertEqual(len(job_feed.dedupe([same_title, other_company, other_role])), 3)

    def test_two_vacancies_at_one_company_in_two_places_both_survive(self):
        """Why the key carries a place: merging distinct vacancies is final.

        A company advertising one title in two cities is advertising two jobs, and
        only one row per key is ever indexed — so collapsing them would not merely
        hide a duplicate, it would delete a vacancy the boards had published.
        """
        pune = posting_fixture("a", "Software Engineer", "Acme", "one", location="Pune, India")
        hyderabad = posting_fixture(
            "b", "Software Engineer", "Acme", "two", location="Hyderabad, India"
        )
        self.assertEqual(len(job_feed.dedupe([pune, hyderabad])), 2)

    def test_two_boards_wording_a_place_differently_cost_a_duplicate(self):
        """The price of that key, asserted rather than left implicit.

        The same opening written up in two places stays two rows. That is the way
        to err: a duplicate is visible and its card names the board it came from,
        whereas a merged-away vacancy is simply gone.
        """
        india = posting_fixture("a", "Platform Engineer", "Acme", "one", location="India, Singapore")
        berlin = posting_fixture("b", "Platform Engineer", "Acme", "two", location="Berlin")
        self.assertEqual(len(job_feed.dedupe([india, berlin])), 2)


class CollectTests(unittest.TestCase):
    """`_get_json` (the only network call) is replaced, so these run offline.

    These are the *single-feed* boards — one paged feed each — so they are read by
    naming the two of them; Adzuna's several market feeds are exercised in
    `AdzunaCollectionTests` below.
    """

    SINGLE_FEED = (job_feed.SOURCE_HIMALAYAS, job_feed.SOURCE_ARBEITNOW)

    def _paged_get(self, pages, calls):
        def _get(url, params=None):
            params = dict(params or {})
            calls.append((url, params))
            if "himalayas" in url:
                return {"jobs": pages["himalayas"].get(params.get("offset", 0), [])}
            return {"data": pages["arbeitnow"].get(params.get("page", 1), [])}
        return _get

    def _run(self, pages, limit, sources=SINGLE_FEED):
        calls = []
        small_pages = {job_feed.SOURCE_HIMALAYAS: 2, job_feed.SOURCE_ARBEITNOW: 2}
        with mock.patch.object(job_feed, "_get_json", self._paged_get(pages, calls)), \
                mock.patch.object(job_feed, "_pause", lambda *_: None), \
                mock.patch.dict(job_feed.PAGE_SIZE, small_pages):
            postings = job_feed.collect(limit=limit, sources=sources)
        return postings, calls

    def test_it_pages_until_the_limit_is_met(self):
        himalayas = {
            0: [dict(HIMALAYAS_RAW, title="Role One", guid="g1"),
                dict(HIMALAYAS_RAW, title="Role Two", guid="g2")],
            2: [dict(HIMALAYAS_RAW, title="Role Three", guid="g3")],
        }
        postings, calls = self._run({"himalayas": himalayas}, limit=3)
        self.assertEqual([p["title"] for p in postings], ["Role One", "Role Two", "Role Three"])
        self.assertEqual(len(calls), 2, "the second page satisfies the limit")

    def test_it_respects_the_limit_and_the_source_order(self):
        himalayas = {0: [dict(HIMALAYAS_RAW, title="Role One", guid="g1"),
                         dict(HIMALAYAS_RAW, title="Role Two", guid="g2")]}
        arbeitnow = {1: [ARBEITNOW_RAW, dict(ARBEITNOW_RAW, slug="s2", title="Second")]}
        postings, calls = self._run({"himalayas": himalayas, "arbeitnow": arbeitnow}, limit=2)
        self.assertEqual(len(postings), 2)
        self.assertTrue(all(call[0] == job_feed.HIMALAYAS_URL for call in calls))

    def test_duplicates_across_boards_are_collapsed(self):
        """Two boards carrying one opening, written the same way, are one posting."""
        himalayas = {0: [dict(HIMALAYAS_RAW, title="Platform Engineer", companyName="Nimbus Labs",
                              locationRestrictions=["Berlin"], guid="g1")]}
        arbeitnow = {1: [dict(ARBEITNOW_RAW, title="Platform Engineer",
                              company_name="Nimbus Labs", location="Berlin")]}
        postings, _ = self._run({"himalayas": himalayas, "arbeitnow": arbeitnow}, limit=10)
        self.assertEqual(len(postings), 1)

    def test_a_board_being_down_does_not_sink_the_others(self):
        def _flaky(url, params=None):
            if "himalayas" in url:
                return {"jobs": [dict(HIMALAYAS_RAW, title="Still Here", guid="g1")]}
            raise RuntimeError("arbeitnow is unreachable")

        progress = []
        with mock.patch.object(job_feed, "_get_json", _flaky), \
                mock.patch.object(job_feed, "_pause", lambda *_: None):
            postings = job_feed.collect(
                limit=10,
                sources=self.SINGLE_FEED,
                on_progress=lambda source, count, error: progress.append((source, error)),
            )
        self.assertEqual([p["title"] for p in postings], ["Still Here"])
        self.assertEqual([name for name, _ in progress], ["himalayas", "arbeitnow"])
        self.assertIn("unreachable", dict(progress)["arbeitnow"])

    def test_a_source_that_stops_early_ends_the_paging(self):
        postings, calls = self._run({"himalayas": {0: []}}, limit=5, sources=["himalayas"])
        self.assertEqual(postings, [])
        self.assertEqual(len(calls), 1)

    def test_a_boards_page_ceiling_is_read_to_its_last_page(self):
        """Depth is a constant, not a hope: the last page the ceiling allows is read.

        A posting buried at the final offset still comes back, and the harvest asks
        for exactly `MAX_PAGES` pages — no more (politeness) and no fewer (stopping
        early would make the ceiling a decoration).
        """
        page_size = job_feed.PAGE_SIZE[job_feed.SOURCE_HIMALAYAS]
        pages = job_feed.MAX_PAGES[job_feed.SOURCE_HIMALAYAS]
        deepest = (pages - 1) * page_size
        himalayas = {
            offset: [
                dict(HIMALAYAS_RAW, title=f"Role {offset + index}", guid=f"g{offset + index}")
                for index in range(page_size)
            ]
            for offset in range(0, deepest + 1, page_size)
        }
        himalayas[deepest] = [dict(HIMALAYAS_RAW, title="Deep Role", guid="deep")] + (
            himalayas[deepest][1:]
        )

        calls = []
        with mock.patch.object(job_feed, "_get_json", self._paged_get({"himalayas": himalayas}, calls)), \
                mock.patch.object(job_feed, "_pause", lambda *_: None):
            postings = job_feed.collect(limit=job_feed.HARVEST_LIMIT, sources=[job_feed.SOURCE_HIMALAYAS])

        self.assertIn("Deep Role", [posting["title"] for posting in postings])
        self.assertEqual(len(calls), pages)

    def test_saving_and_loading_round_trips(self):
        directory = tempfile.mkdtemp(prefix="careercompass_jobs_")
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        path = os.path.join(directory, "job_postings.json")
        job_feed.save([PLATFORM, DESIGNER], path)
        self.assertEqual(job_feed.load(path), [PLATFORM, DESIGNER])
        with open(path, encoding="utf-8") as handle:
            artifact = json.load(handle)
        # The artifact is an object now: it carries the postings *and* when they
        # were harvested (see `test_job_freshness`), not a bare list.
        self.assertEqual(artifact["postings"], [PLATFORM, DESIGNER])
        self.assertTrue(artifact["harvested_at"])


class AdzunaCollectionTests(unittest.TestCase):
    """Adzuna's side of the harvest: credentials, the market plan, and its paging.

    `_get_json` is replaced, so the pages are the test's — but the URL and query of
    every request are captured, because that is where the market, the category, the
    sort order and the credentials actually land, and none of it is visible in the
    postings that come back.

    The credentials are the test's own, set through the environment: an Adzuna
    harvest is *off* until a key is configured, and that switch is behaviour worth
    pinning down rather than arranging around.
    """

    #: Set for every test here, so a developer with real keys in their own `.env`
    #: gets the same run as one without any.
    CREDENTIALS = {"ADZUNA_APP_ID": "test-app-id", "ADZUNA_APP_KEY": "test-app-key"}

    def _feeding(self, calls, per_page=2):
        """A market that answers `per_page` adverts on every page it is asked for."""
        def _get(url, params=None):
            calls.append((url, dict(params or {})))
            page = url.rsplit("/", 1)[-1]
            label = f"{len(calls)}-{page}"
            return {
                "results": [
                    dict(ADZUNA_RAW, id=f"{label}-{index}", title=f"Advert {label}-{index}")
                    for index in range(per_page)
                ]
            }
        return _get

    def _nothing(self, calls):
        """A market that has nothing left, whenever it is asked."""
        def _get(url, params=None):
            calls.append((url, dict(params or {})))
            return {"results": []}
        return _get

    def _fetch(self, get, limit=None, sources=(job_feed.SOURCE_ADZUNA,)):
        with mock.patch.dict(os.environ, self.CREDENTIALS), \
                mock.patch.object(job_feed, "_get_json", get), \
                mock.patch.object(job_feed, "_pause", lambda *_: None):
            return job_feed.collect(
                limit=limit or job_feed.HARVEST_LIMIT, sources=list(sources)
            )

    def test_the_market_is_read_whole_and_then_city_by_city(self):
        """India-wide first, then a query per hub, then one for remote.

        Adzuna has no "everything new" feed to walk, so paging *is* the plan: a hub
        is the only way to see what that hub holds, and the nationwide newest rows
        are not the newest rows in Bangalore.
        """
        calls = []
        postings = self._fetch(self._feeding(calls))
        self.assertEqual(len(calls), len(job_feed.ADZUNA_QUERIES))
        self.assertEqual(len(postings), len(job_feed.ADZUNA_QUERIES) * 2)
        urls = [url for url, _ in calls]
        self.assertTrue(all("/jobs/in/search/" in url for url in urls), urls[0])
        asked = [params.get("where") for _, params in calls]
        self.assertIn(None, asked, "India-wide is a query of its own")
        self.assertIn("Bangalore", asked)
        self.assertIn("Mumbai", asked)
        self.assertEqual(
            [params.get("what") for _, params in calls].count("remote"), 1,
            "one query asks for the remote adverts the API has no filter for",
        )

    def test_every_request_carries_the_credentials_the_market_and_the_order(self):
        calls = []
        self._fetch(self._feeding(calls))
        self.assertTrue(calls)
        for _, params in calls:
            self.assertEqual(params["app_id"], "test-app-id")
            self.assertEqual(params["app_key"], "test-app-key")
            self.assertEqual(params["category"], "it-jobs")
            self.assertEqual(params["sort_by"], "date")
            # No direction is asked for: Adzuna rejects every `sort_dir` value with a
            # 400, and `sort_by=date` already answers newest-first.
            self.assertNotIn("sort_dir", params)
            self.assertEqual(
                params["results_per_page"], job_feed.PAGE_SIZE[job_feed.SOURCE_ADZUNA]
            )
            self.assertEqual(params["max_days_old"], job_feed.ADZUNA_MAX_DAYS_OLD)

    def test_pages_are_numbered_in_the_path_rather_than_a_parameter(self):
        calls = []
        postings = self._fetch(
            self._feeding(calls, per_page=job_feed.PAGE_SIZE[job_feed.SOURCE_ADZUNA]),
            limit=60,
        )
        urls = [url for url, _ in calls]
        self.assertTrue(urls[0].endswith("/search/1"))
        self.assertTrue(urls[1].endswith("/search/2"))
        self.assertEqual(len(postings), 60, "the limit bounds the harvest, not the feed")

    def test_a_query_with_nothing_left_does_not_end_the_board(self):
        """One empty page is one query exhausted, not the market exhausted.

        The plan reads a hub that has nothing new and goes on to the next one; the
        alternative — stopping the board — is how a city that is simply quiet would
        silently cancel every market after it.
        """
        calls = []
        postings = self._fetch(self._nothing(calls))
        self.assertEqual(postings, [])
        self.assertEqual(len(calls), len(job_feed.ADZUNA_QUERIES))

    def test_the_market_and_the_sector_are_configurable(self):
        """`ADZUNA_COUNTRY` moves the market, `ADZUNA_CATEGORY=` widens the sector."""
        calls = []
        with mock.patch.dict(
            os.environ, {**self.CREDENTIALS, "ADZUNA_COUNTRY": "gb", "ADZUNA_CATEGORY": ""}
        ), mock.patch.object(job_feed, "_get_json", self._feeding(calls)), \
                mock.patch.object(job_feed, "_pause", lambda *_: None):
            postings = job_feed.collect(limit=10, sources=[job_feed.SOURCE_ADZUNA])
        self.assertTrue(all("/jobs/gb/search/" in url for url, _ in calls))
        self.assertTrue(all("category" not in params for _, params in calls))
        self.assertEqual(postings[0]["salary_currency"], "GBP", "the market's money")

    def test_missing_credentials_are_a_named_reason_not_a_crash(self):
        with mock.patch.dict(os.environ, {"ADZUNA_APP_ID": "", "ADZUNA_APP_KEY": ""}):
            with self.assertRaises(job_feed.SourceUnavailable) as caught:
                job_feed.fetch_source(job_feed.SOURCE_ADZUNA, 10)
        self.assertIn("ADZUNA_APP_ID", str(caught.exception))
        self.assertIn("ADZUNA_APP_KEY", str(caught.exception))

    def test_an_unconfigured_adzuna_leaves_the_rest_of_the_harvest_alone(self):
        """No key is not a failure: the boards that need none still load, and the
        reason travels back with the harvest so the page can report it."""
        progress = []

        def _himalayas_only(url, params=None):
            return {"jobs": [HIMALAYAS_RAW]}

        with mock.patch.dict(os.environ, {"ADZUNA_APP_ID": "", "ADZUNA_APP_KEY": ""}), \
                mock.patch.object(job_feed, "_get_json", _himalayas_only), \
                mock.patch.object(job_feed, "_pause", lambda *_: None):
            postings = job_feed.collect(
                limit=10,
                on_progress=lambda source, count, error: progress.append((source, count, error)),
            )
        self.assertEqual([p["title"] for p in postings], [HIMALAYAS_RAW["title"]])
        self.assertEqual([name for name, _, _ in progress], list(job_feed.SOURCES))
        reported = {name: error for name, _, error in progress}
        self.assertIn("ADZUNA_APP_ID", reported[job_feed.SOURCE_ADZUNA])
        self.assertEqual(reported[job_feed.SOURCE_HIMALAYAS], "")

    def test_the_plan_stays_inside_the_free_tier(self):
        """Adzuna's free access allows 25 hits a minute and 250 a day.

        The plan is a budget as much as a coverage decision: one harvest has to fit
        inside the per-minute allowance, and the day has to afford several of them,
        or a failed run could not be repeated until tomorrow.
        """
        budget = sum(int(query.get("pages") or 0) for query in job_feed.ADZUNA_QUERIES)
        self.assertLessEqual(budget, 25, "one harvest inside the per-minute allowance")
        self.assertLessEqual(budget * 8, 250, "the day affords a handful of runs")


class RefusedCredentialTests(unittest.TestCase):
    """A key a board refuses must not be published by the report of the refusal.

    httpx quotes the whole URL — query string included — in the error it raises for
    a bad status, and Adzuna's app id and key ride in that query. That message is
    not private: `collect` records it, `save` writes it into the artifact, the ingest
    puts it in the index sidecar, and `/jobs/search` serves it. So these drive the
    *real* `_get_json`, replacing only the HTTP call beneath it — swapping out the
    function under test is exactly how a fix like this passes a test while leaving
    the leak in place.
    """

    CREDENTIALS = {
        "ADZUNA_APP_ID": "abcdef123456",
        "ADZUNA_APP_KEY": "0123456789abcdef0123456789abcdef",
    }

    def _refusing(self, status: int = 401):
        """What `httpx.get` hands back when a board rejects the harvest's key."""
        def _get(url, **kwargs):
            request = httpx.Request("GET", url, params=kwargs.get("params"))
            return httpx.Response(status, request=request)
        return _get

    def _harvest(self):
        progress = []
        with mock.patch.dict(os.environ, self.CREDENTIALS), \
                mock.patch.object(httpx, "get", self._refusing()), \
                mock.patch.object(job_feed, "_pause", lambda *_: None):
            postings = job_feed.collect(
                limit=10,
                sources=[job_feed.SOURCE_ADZUNA],
                on_progress=lambda source, count, error: progress.append(
                    (source, count, error)
                ),
            )
        return postings, progress

    def test_a_refused_key_is_not_reproduced_in_the_harvests_report(self):
        postings, progress = self._harvest()
        self.assertEqual(postings, [])
        source, count, error = progress[0]
        self.assertEqual((source, count), (job_feed.SOURCE_ADZUNA, 0))
        self.assertNotIn(self.CREDENTIALS["ADZUNA_APP_KEY"], error)
        self.assertNotIn(self.CREDENTIALS["ADZUNA_APP_ID"], error)
        self.assertIn("401", error, "the failure itself is still reported")
        self.assertIn("api.adzuna.com", error, "and which endpoint refused it")

    def test_what_is_written_to_disk_holds_no_credential_either(self):
        """The artifact is data at rest and gets copied around; it is scrubbed too."""
        postings, progress = self._harvest()
        directory = tempfile.mkdtemp(prefix="careercompass_redaction_")
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = os.path.join(directory, "job_postings.json")
        job_feed.save(
            postings,
            path,
            sources=[
                {"source": name, "postings": count, "error": error}
                for name, count, error in progress
            ],
        )
        with open(path, encoding="utf-8") as handle:
            written = handle.read()
        self.assertNotIn(self.CREDENTIALS["ADZUNA_APP_KEY"], written)
        self.assertNotIn(self.CREDENTIALS["ADZUNA_APP_ID"], written)

    def test_a_credential_already_in_an_index_is_not_served(self):
        """An index written before the feed stopped quoting the query is still safe.

        The notice is unauthenticated, so the scrub happens where the record is read
        out as well as where it is made: an old artifact must not be able to publish
        a key just because it outlived the bug.
        """
        key = self.CREDENTIALS["ADZUNA_APP_KEY"]
        app_id = self.CREDENTIALS["ADZUNA_APP_ID"]
        served = None
        with mock.patch.dict(os.environ, self.CREDENTIALS):
            served = job_service.source_status(
                {
                    "sources": [
                        {
                            "source": job_feed.SOURCE_ADZUNA,
                            "postings": 0,
                            "error": (
                                "401 Unauthorized from https://api.adzuna.com/v1/api/"
                                f"jobs/in/search/1?app_id={app_id}&app_key={key}"
                            ),
                        }
                    ]
                }
            )
        self.assertNotIn(key, served[0]["error"])
        self.assertNotIn(app_id, served[0]["error"])
        self.assertIn("401", served[0]["error"])


class RequestAttemptTests(unittest.TestCase):
    """A transient failure is tried again; a refusal is not.

    A board is read page by page, so one connection dropped part-way through would
    otherwise throw away every page already fetched from it — including all
    twenty-one pages of the plan that reads the home market.
    """

    URL = "https://api.adzuna.com/v1/api/jobs/in/search/1"

    def test_a_dropped_connection_is_retried_until_it_works(self):
        attempts = []

        def _flaky(url, **kwargs):
            attempts.append(url)
            if len(attempts) < 3:
                raise httpx.ConnectError("getaddrinfo failed")
            return httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", url))

        with mock.patch.object(httpx, "get", _flaky), \
                mock.patch.object(job_feed, "_pause", lambda *_: None):
            payload = job_feed._get_json(self.URL, {"what": "developer"})
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(len(attempts), 3, "it kept trying rather than giving up")

    def test_a_server_error_is_retried_like_a_dropped_connection(self):
        attempts = []

        def _unwell(url, **kwargs):
            attempts.append(url)
            status = 503 if len(attempts) < job_feed.REQUEST_ATTEMPTS else 200
            return httpx.Response(status, json={"ok": True}, request=httpx.Request("GET", url))

        with mock.patch.object(httpx, "get", _unwell), \
                mock.patch.object(job_feed, "_pause", lambda *_: None):
            payload = job_feed._get_json(self.URL)
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(len(attempts), job_feed.REQUEST_ATTEMPTS)

    def test_a_refusal_is_asked_once_and_not_again(self):
        """A 400 is a wrong request, not a bad moment; retrying buys nothing."""
        attempts = []

        def _refusing(url, **kwargs):
            attempts.append(url)
            return httpx.Response(400, request=httpx.Request("GET", url))

        with mock.patch.object(httpx, "get", _refusing), \
                mock.patch.object(job_feed, "_pause", lambda *_: None):
            with self.assertRaises(job_feed.SourceUnavailable) as caught:
                job_feed._get_json(self.URL)
        self.assertEqual(len(attempts), 1, "a 400 will not become a 200")
        self.assertIn("400", str(caught.exception))

    def test_a_failure_that_outlasts_the_attempts_names_the_board(self):
        attempts = []

        def _always_down(url, **kwargs):
            attempts.append(url)
            raise httpx.ConnectError("getaddrinfo failed")

        with mock.patch.object(httpx, "get", _always_down), \
                mock.patch.object(job_feed, "_pause", lambda *_: None):
            with self.assertRaises(job_feed.SourceUnavailable) as caught:
                job_feed._get_json(self.URL)
        self.assertEqual(len(attempts), job_feed.REQUEST_ATTEMPTS)
        self.assertIn("ConnectError", str(caught.exception))
        self.assertIn("api.adzuna.com", str(caught.exception))


class IngestJobsTests(IndexBackedTest):
    """The collection itself: naming, the space guard, and not eating neighbours."""

    def _ingest(self, postings, rebuild=False, limit=100):
        directory = tempfile.mkdtemp(prefix="careercompass_jobs_")
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        path = os.path.join(directory, "job_postings.json")
        job_feed.save(postings, path)
        with contextlib.redirect_stdout(io.StringIO()):
            return ingest_jobs.ingest(limit=limit, from_file=path, save_path="", rebuild=rebuild)

    def test_postings_land_in_the_job_role_collection(self):
        result = self._ingest([PLATFORM, DESIGNER])
        self.assertEqual(result["written"], 2)
        self.assertEqual(vector_store.count_points("job_role"), 2)
        self.assertEqual(result["status"]["collection"], "job_role")

    def test_the_embedding_space_is_recorded_next_to_the_collection(self):
        self._ingest([PLATFORM])
        self.assertEqual(vector_store.recorded_space("job_role"), embeddings.signature())

    def test_the_ingest_creates_the_payload_indexes_the_filters_read(self):
        """Embedded Qdrant ignores payload indexes; a server-backed one needs them."""
        result = self._ingest([PLATFORM, DESIGNER])
        self.assertEqual(
            sorted(result["status"]["payload_indexes"]), sorted(job_service.FILTER_INDEXES)
        )

    def test_the_ingest_records_what_each_board_contributed(self):
        """The `sources` block the API reports has to be written down at ingest time.

        Only the ingest hears from a board that failed, so the sidecar is the one
        place "Adzuna was never configured" can survive to be read at request time.
        """
        himalayas = posting_fixture(
            "himalayas:platform", "Platform Engineer", "Nimbus", "Run it.", source="himalayas"
        )
        result = self._ingest([PLATFORM, DESIGNER, himalayas])
        recorded = vector_store.recorded_meta("job_role")["sources"]
        self.assertEqual(
            [(entry["source"], entry["postings"]) for entry in recorded],
            [("arbeitnow", 2), ("himalayas", 1)],
        )
        self.assertEqual(result["status"]["sources"], recorded)

    def test_a_live_harvest_writes_the_board_record_into_the_saved_file(self):
        """What makes `--from-file` as informative as the live run that wrote it.

        `_collect` holds each board's outcome while it fetches and nothing else ever
        sees it, so the save has to carry it: a served artifact has no network on
        which to ask a board again, and "Adzuna was never configured" is exactly the
        fact that has to survive the trip.
        """
        def _get(url, params=None):
            params = dict(params or {})
            if "himalayas" in url:
                return {"jobs": [HIMALAYAS_RAW] if not params.get("offset") else []}
            raise RuntimeError("arbeitnow is unreachable")

        directory = tempfile.mkdtemp(prefix="careercompass_jobs_artifact_")
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        path = os.path.join(directory, "job_postings.json")
        with mock.patch.object(job_feed, "_get_json", _get), \
                mock.patch.object(job_feed, "_pause", lambda *_: None), \
                contextlib.redirect_stdout(io.StringIO()):
            ingest_jobs._collect(
                limit=10,
                sources=[job_feed.SOURCE_HIMALAYAS, job_feed.SOURCE_ARBEITNOW],
                from_file="",
                save_path=path,
            )
        recorded = job_feed.load_artifact(path)["sources"]
        self.assertEqual([entry["source"] for entry in recorded], ["himalayas", "arbeitnow"])
        self.assertEqual(recorded[0]["postings"], 1)
        self.assertIn("unreachable", recorded[1]["error"])

    def test_reingesting_updates_instead_of_duplicating(self):
        self._ingest([PLATFORM, DESIGNER])
        self._ingest([PLATFORM, DESIGNER])
        self.assertEqual(vector_store.count_points("job_role"), 2)

    def test_search_finds_the_platform_posting_over_the_design_one(self):
        self._ingest([PLATFORM, DESIGNER])
        hits = vector_store.search_records("job_role", "kubernetes platform engineer", limit=2)
        self.assertEqual(hits[0][1]["id"], PLATFORM["id"])

    def test_an_incompatible_embedding_space_is_refused_not_mixed(self):
        """`job_role` is a fixed name, so the space guard is what protects it."""
        self._ingest([PLATFORM])
        vector_store.record_space("job_role", "gemini-gemini-embedding-001-768")
        with self.assertRaises(SystemExit) as caught:
            self._ingest([DESIGNER])
        self.assertIn("--rebuild", str(caught.exception))
        self.assertEqual(vector_store.count_points("job_role"), 1, "nothing was added")

    def test_rebuilding_switches_the_space(self):
        self._ingest([PLATFORM, DESIGNER])
        vector_store.record_space("job_role", "gemini-gemini-embedding-001-768")
        self._ingest([DESIGNER], rebuild=True)
        self.assertEqual(vector_store.recorded_space("job_role"), embeddings.signature())
        self.assertEqual(vector_store.count_points("job_role"), 1)

    def test_rebuilding_job_postings_leaves_the_role_index_alone(self):
        """The catalog index and the live feed share one store, not one fate."""
        vector_store.upsert_roles([role_fixture("fixture_devops", "Cloud DevOps Engineer",
                                                ["Cloud, DevOps & Linux"], ["Docker"])])
        self._ingest([PLATFORM, DESIGNER], rebuild=True)
        status = vector_store.index_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["points"], 1, "the curated role index must survive")

    def test_an_empty_harvest_writes_nothing(self):
        with self.assertRaises(SystemExit) as caught:
            self._ingest([])
        self.assertIn("Nothing was written", str(caught.exception))
        self.assertFalse(os.path.exists(os.path.join(vector_store.index_path(), "job_role.space")))


if __name__ == "__main__":
    unittest.main()
