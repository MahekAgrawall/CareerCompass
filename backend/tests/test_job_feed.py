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
import io
import json
import os
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


def posting_fixture(identifier, title, company, description, **overrides):
    posting = {
        "id": identifier,
        "source": "arbeitnow",
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
        self.assertEqual(posting["description"], "Own Figma design systems.")
        self.assertEqual(posting["location"], "Berlin")
        self.assertEqual(posting["employment_type"], "full-time")
        self.assertTrue(posting["remote"])
        self.assertEqual(posting["published"], "2026-10-17")
        self.assertEqual(posting["salary_min"], None)

    def test_arbeitnow_location_falls_back_to_remote(self):
        raw = dict(ARBEITNOW_RAW, location="", remote=True)
        self.assertEqual(job_feed.normalise_arbeitnow(raw)["location"], "Remote")

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


class CollectTests(unittest.TestCase):
    """`_get_json` (the only network call) is replaced, so these run offline."""

    def _paged_get(self, pages, calls):
        def _get(url, params=None):
            params = dict(params or {})
            calls.append((url, params))
            if "himalayas" in url:
                return {"jobs": pages["himalayas"].get(params.get("offset", 0), [])}
            return {"data": pages["arbeitnow"].get(params.get("page", 1), [])}
        return _get

    def _run(self, pages, limit, sources=job_feed.SOURCES):
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
        himalayas = {0: [dict(HIMALAYAS_RAW, title="Platform Engineer", guid="g1")]}
        arbeitnow = {1: [dict(ARBEITNOW_RAW, title="Platform Engineer",
                              company_name="Nimbus Labs")]}
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
                limit=10, on_progress=lambda source, count, error: progress.append((source, error)),
            )
        self.assertEqual([p["title"] for p in postings], ["Still Here"])
        self.assertEqual([name for name, _ in progress], ["himalayas", "arbeitnow"])
        self.assertIn("unreachable", dict(progress)["arbeitnow"])

    def test_a_source_that_stops_early_ends_the_paging(self):
        postings, calls = self._run({"himalayas": {0: []}}, limit=5, sources=["himalayas"])
        self.assertEqual(postings, [])
        self.assertEqual(len(calls), 1)

    def test_himalayas_is_read_deep_enough_for_the_places_it_lists_thinly(self):
        """Roughly one Himalayas listing in thirty names India, so a shallow read of
        the newest rows finds almost none of it — the depth is what buys the market.
        A posting buried at the last offset the budget covers still comes back.
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
            postings = job_feed.collect(limit=2000, sources=[job_feed.SOURCE_HIMALAYAS])

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
