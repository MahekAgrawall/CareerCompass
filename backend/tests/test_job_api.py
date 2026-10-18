"""The `/jobs/search` endpoint — the read path over the live postings.

What this pins down:

* the endpoint is public, like `/roles`, and needs no account;
* results come from the `job_role` collection and never from the curated role
  index sitting beside it in the same store;
* the search box's words are a **filter**: only postings that say every one of
  them come back, and when none says all of them the search loosens to any of
  them and reports it (`relaxed`), because a dead end is worse than a loose page;
* ranking is the index's cosine, lifted by a query word appearing in a posting's
  title (reported back as `matched_terms`), so a search box answers with the
  posting that says what was typed;
* `/jobs/locations` offers the places the collection actually names, commonest
  first, each count asked of the same filter a search with it applies;
* location, work arrangement, experience, employment type and posting date are
  applied by the vector store and the words are narrowed against the payloads it
  holds, so together they decide `matched` over the whole collection rather than
  over the page;
* a posting that carries no publication date is *excluded* by a "posted within"
  filter rather than let through on a technicality;
* a filter-only browse still works (the filter words stand in for the query), and
  asking for nothing at all is a 400;
* with no index built, the endpoint still answers honestly (`available: false`)
  rather than erroring or inventing a weaker search — including when the index
  *data* is there but the `qdrant-client` package is not, which is a deployment
  shape that used to raise out of the store filter;
* the response says what each provider contributed to the harvest and why any of
  them is missing, so a thin feed can be explained instead of merely observed;
* the inputs are validated, so an unknown experience or employment bucket is
  refused, and the route's literal stays in step with the service's vocabulary.

Isolation (throwaway database and vector index) comes from `tests.harness`; the
posting fixtures are shared with `test_job_feed`.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from tests.harness import IndexBackedTest, client  # noqa: F401  (isolation first)
from tests.test_classification import (  # noqa: E402
    answer,
    clear_store,
    fake_model,
    using,
)
from tests.test_job_feed import DESIGNER, PLATFORM, posting_fixture, role_fixture  # noqa: E402

from app import dependencies  # noqa: E402
from services import (  # noqa: E402
    ai_service,
    career_service,
    job_feed,
    job_service,
    vector_store,
)

QUERY = "kubernetes platform engineer"
PAID = posting_fixture(
    "arbeitnow:paid-role",
    "Kubernetes Platform Engineer",
    "Conflux",
    "Own our Kubernetes platform, Terraform modules and cloud infrastructure.",
    categories=["Infrastructure"],
    seniority=["Senior"],
    salary_min=90000,
    salary_max=120000,
    salary_currency="USD",
    salary_period="annual",
)

# Five postings that differ on exactly the axes the filters read, so each
# assertion below can name the postings it expects rather than count them.
BERLIN = posting_fixture(
    "arbeitnow:berlin-senior",
    "Senior Kubernetes Engineer",
    "Spree Cloud",
    "Operate Kubernetes clusters and Terraform modules for our Berlin platform.",
    location="Berlin, Germany",
    remote=False,
)
UTRECHT = posting_fixture(
    "himalayas:utrecht-senior",
    "Senior Platform Engineer",
    "Canal Systems",
    "Own the Kubernetes platform and our Terraform deployment pipeline.",
    location="Utrecht, Netherlands",
    remote=True,
)
STUDENT = posting_fixture(
    "arbeitnow:data-student",
    "Working Student Data Analyst",
    "Munich Metrics",
    "Help the analytics team with dashboards and SQL reports.",
    location="Munich, Germany",
    remote=False,
    employment_type="working student",
)
JUNIOR = posting_fixture(
    "arbeitnow:junior-analyst",
    "Junior Data Analyst",
    "Cape Insights",
    "Build dashboards and SQL reports for the analytics team.",
    location="Pune, India",
    remote=False,
)
FILTERED = [BERLIN, UTRECHT, STUDENT, JUNIOR]


def days_ago(days: int) -> str:
    """A publication date `days` before today, in the form a posting carries.

    Built relative to the clock rather than pinned to a literal, because the
    "posted within" filter compares against *now* by definition: a fixture with a
    fixed date would pass today and start failing next month.
    """
    today = datetime.now(timezone.utc).date()
    return (today - timedelta(days=days)).isoformat()


# Three postings that say the same thing and differ only in how old they are —
# plus one no board dated at all, which is the case a date filter must exclude
# rather than let through on a technicality.
RECENT = posting_fixture(
    "adzuna:recent", "Kubernetes Engineer", "Deccan Cloud",
    "Operate Kubernetes.", location="Pune, India", remote=False, published=days_ago(2),
)
OLD = posting_fixture(
    "arbeitnow:old", "Kubernetes Engineer", "Rhine Cloud",
    "Operate Kubernetes.", location="Bonn, Germany", remote=False, published=days_ago(45),
)
UNDATED = posting_fixture(
    "himalayas:undated", "Kubernetes Engineer", "Veldt Cloud",
    "Operate Kubernetes.", location="Cape Town, South Africa", remote=False, published="",
)
DATES = [RECENT, OLD, UNDATED]

# Employment wording as the boards actually send it: Adzuna's two halves joined,
# Arbeitnow's hyphenated token, Himalayas' one-word label, and an internship the
# experience vocabulary also reads.
FULL_TIME_JOB = posting_fixture(
    "adzuna:full-time", "Kubernetes Engineer", "Deccan Cloud", "Operate Kubernetes.",
    location="Pune, India", employment_type="full time, permanent",
)
PART_TIME_JOB = posting_fixture(
    "arbeitnow:part-time", "Kubernetes Engineer", "Bright Studio", "Operate Kubernetes.",
    location="Berlin, Germany", employment_type="part-time",
)
CONTRACT_JOB = posting_fixture(
    "himalayas:contract", "Kubernetes Engineer", "Nimbus Labs", "Operate Kubernetes.",
    location="Remote", employment_type="Contractor",
)
INTERNSHIP = posting_fixture(
    "adzuna:internship", "Kubernetes Engineer Internship", "Deccan Cloud",
    "Operate Kubernetes.", location="Pune, India", employment_type="Internship",
)
EMPLOYMENTS = [FULL_TIME_JOB, PART_TIME_JOB, CONTRACT_JOB, INTERNSHIP]


class JobSearchApiTests(IndexBackedTest):
    def _index_postings(self, postings):
        rows = [
            (row["record_id"], row["document"], row["payload"])
            for row in job_feed.rows(postings)
        ]
        return vector_store.upsert_records(vector_store.JOBS_COLLECTION, rows)

    def _search(self, query=QUERY, **params):
        return client.get("/jobs/search", params={"q": query, **params})

    def test_without_an_index_the_endpoint_says_so_instead_of_erroring(self):
        response = self._search()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["available"])
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["results"], [])
        self.assertEqual(body["query"], QUERY)

    def test_index_data_without_the_client_answers_instead_of_erroring(self):
        """The deployment shape that used to 500: data present, client absent.

        `is_available()` only looks at the index *directory*, so a process without
        `qdrant-client` still reports an index; the store filter was built before
        that was known and its `from qdrant_client import models` escaped the
        request as a 500. Only the filters' guard changed — the answer is the same
        `available: false` every other unindexed read gives.
        """
        os.makedirs(os.environ["QDRANT_PATH"], exist_ok=True)
        with open(os.path.join(os.environ["QDRANT_PATH"], "placeholder"), "w") as handle:
            handle.write("a non-empty index directory is all is_available() checks\n")
        self.assertTrue(vector_store.is_available())
        with mock.patch.dict(
            sys.modules, {"qdrant_client": None, "qdrant_client.models": None}
        ):
            response = self._search(location="Berlin")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["available"])
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["matched"], 0)
        self.assertEqual(body["indexed"], 0)
        self.assertEqual(body["results"], [])

    def test_results_are_the_nearest_postings(self):
        """The postings that say the words, nearest first.

        The designer is indexed and the index has an opinion about it, but it says
        none of "kubernetes platform engineer" — and the words are a condition, so
        it is not a result at all (see
        `test_a_posting_that_never_says_the_word_is_not_a_result`).
        """
        self._index_postings([PLATFORM, DESIGNER])
        body = self._search().json()
        self.assertTrue(body["available"])
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["matched"], 1)
        self.assertEqual([item["id"] for item in body["results"]], [PLATFORM["id"]])
        first = body["results"][0]
        self.assertEqual(first["id"], PLATFORM["id"])
        self.assertEqual(first["title"], "Senior Platform Engineer")
        self.assertEqual(first["company"], "Nimbus Labs")
        self.assertEqual(first["url"], PLATFORM["url"])
        self.assertEqual(first["source"], PLATFORM["source"])
        self.assertIsInstance(first["similarity"], float)

    def test_a_posting_carries_everything_a_card_needs(self):
        self._index_postings([PAID])
        item = self._search("kubernetes terraform", limit=1).json()["results"][0]
        self.assertEqual(item["salary_text"], "USD 90000-120000 / annual")
        self.assertEqual(item["seniority"], ["Senior"])
        self.assertEqual(item["categories"], ["Infrastructure"])
        self.assertTrue(item["remote"])
        self.assertTrue(item["excerpt"])

    def test_postings_never_bleed_in_from_the_catalog_index(self):
        """Both collections share one store; the endpoint must only read one."""
        vector_store.upsert_roles([
            role_fixture("fixture_platform", "Kubernetes Platform Engineer",
                         ["Cloud, DevOps & Linux"], ["Kubernetes", "Terraform"]),
        ])
        self._index_postings([PLATFORM])
        body = self._search().json()
        self.assertEqual([item["id"] for item in body["results"]], [PLATFORM["id"]])

    def test_the_catalog_alone_does_not_make_postings_available(self):
        vector_store.upsert_roles([
            role_fixture("fixture_platform", "Kubernetes Platform Engineer",
                         ["Cloud, DevOps & Linux"], ["Kubernetes"]),
        ])
        body = self._search().json()
        self.assertFalse(body["available"])
        self.assertEqual(body["results"], [])

    def test_limit_is_honoured_and_bounded(self):
        # Both say the query's words, so the page is a choice about the *limit*
        # and not about which postings qualified.
        self._index_postings([PLATFORM, PAID])
        self.assertEqual(self._search(limit=1).json()["count"], 1)
        self.assertEqual(self._search(limit=2).json()["count"], 2)
        self.assertEqual(self._search(limit=0).status_code, 422)
        self.assertEqual(self._search(limit=1000).status_code, 422)

    def test_asking_for_nothing_at_all_is_a_400(self):
        self.assertEqual(client.get("/jobs/search").status_code, 400)
        self.assertEqual(client.get("/jobs/search", params={"q": ""}).status_code, 400)
        self.assertEqual(client.get("/jobs/search", params={"q": "   "}).status_code, 400)

    def test_a_filter_alone_is_enough_to_search(self):
        """No search box text — the filter terms become the ranking text."""
        self._index_postings(FILTERED)
        body = self._search("", location="Berlin").json()
        self.assertEqual(body["query"], "Berlin")
        self.assertEqual([item["id"] for item in body["results"]], [BERLIN["id"]])

    def test_an_unknown_experience_bucket_is_refused(self):
        self.assertEqual(self._search(experience="principal").status_code, 422)
        self.assertEqual(self._search(experience="entry").status_code, 200)

    def test_the_endpoint_accepts_every_bucket_the_service_offers(self):
        """The query parameter's literal and the rule table must not drift apart."""
        for level in job_service.EXPERIENCE_LEVELS:
            response = client.get("/jobs/search", params={"q": QUERY, "experience": level})
            self.assertEqual(response.status_code, 200, level)

    def test_the_endpoint_needs_no_account(self):
        """Nothing in this file sends an Authorization header."""
        self.assertEqual(client.get("/jobs/search", params={"q": QUERY}).status_code, 200)

    # ── Ranking ───────────────────────────────────────────────────────────────
    def test_a_title_match_outranks_a_semantically_nearer_posting(self):
        """The store ranks by meaning; a search box also has to rank by saying so.

        `crowded` mentions Python throughout its description, so the index puts it
        nearer the word — and it is still second, because `titled`'s title carries
        it. The cosines are asserted the other way round deliberately: the flip is
        the whole point of the re-rank.
        """
        titled = posting_fixture(
            "arbeitnow:titled-python",
            "Python Software Engineer",
            "Wypoon",
            "Join the team building back-end services for our clients.",
        )
        crowded = posting_fixture(
            "arbeitnow:python-mentions",
            "Generalist Engineer",
            "Broadworks",
            "Python Python Python Python data science machine learning analytics "
            "dashboards python reporting python pipelines.",
        )
        self._index_postings([titled, crowded])
        results = self._search("python").json()["results"]
        self.assertEqual(
            [item["id"] for item in results], [titled["id"], crowded["id"]]
        )
        self.assertLess(results[0]["similarity"], results[1]["similarity"])
        self.assertEqual(results[0]["matched_terms"], ["python"])
        self.assertEqual(results[1]["matched_terms"], [])

    def test_matched_terms_names_the_words_the_title_carried(self):
        self._index_postings(
            [
                posting_fixture(
                    "arbeitnow:titled-python",
                    "Python Software Engineer",
                    "Wypoon",
                    "Join the team building back-end services for our clients.",
                )
            ]
        )
        item = self._search("python engineer").json()["results"][0]
        self.assertEqual(item["matched_terms"], ["python", "engineer"])

    def test_fillers_and_one_letter_words_are_not_matched_on(self):
        self._index_postings(
            [
                posting_fixture(
                    "arbeitnow:titled-python",
                    "Python Software Engineer",
                    "Wypoon",
                    "Join the team building back-end services for our clients.",
                )
            ]
        )
        item = self._search("the a of in python").json()["results"][0]
        self.assertEqual(item["matched_terms"], ["python"])

    def test_a_query_no_title_carries_keeps_the_semantic_order(self):
        """With nothing to lift, the page is exactly the index's own ranking."""
        self._index_postings(FILTERED)
        results = self._search("dashboards sql reports analytics").json()["results"]
        self.assertTrue(results)
        for item in results:
            self.assertEqual(item["matched_terms"], [])
        similarities = [item["similarity"] for item in results]
        self.assertEqual(similarities, sorted(similarities, reverse=True))

    def test_within_a_tier_the_indexs_own_order_decides(self):
        """The matched-word *count* separates tiers; the cosine still separates them."""
        analytics = posting_fixture(
            "arbeitnow:analyst-analytics",
            "Data Analyst",
            "Cape Insights",
            "Build dashboards and SQL reports for the analytics team.",
        )
        admin = posting_fixture(
            "arbeitnow:analyst-admin",
            "Analyst",
            "Quiet Office",
            "General office support, filing and reception duties.",
        )
        self._index_postings([analytics, admin])
        results = self._search("analyst").json()["results"]
        # Both titles carry "analyst", so the tier is the same and meaning decides.
        self.assertEqual([len(item["matched_terms"]) for item in results], [1, 1])
        self.assertEqual(results[0]["id"], analytics["id"])
        self.assertGreaterEqual(results[0]["similarity"], results[1]["similarity"])

    # ── Keywords ──────────────────────────────────────────────────────────────
    def test_a_posting_that_never_says_the_word_is_not_a_result(self):
        """The reported bug: searching "java" in Amsterdam answered with a Dutch
        AI internship.

        The internship is an Amsterdam tech role, so the index places it near the
        search text and the location filter lets it through — but it never says
        Java, and the words are a condition rather than a hint. The keyword filter
        is what removes it.
        """
        java = posting_fixture(
            "arbeitnow:kotlin-java",
            "Kotlin/Java Back-end Engineer",
            "Wypoon",
            "Build back-end services in Kotlin and Java for our platform.",
            location="Amsterdam, Netherlands",
        )
        internship = posting_fixture(
            "arbeitnow:ai-intern",
            "Stage AI & Automatisering",
            "Flagship",
            "Wij automatiseren ons werk met AI en slimme tooling.",
            location="Amsterdam, Noord-Holland, Nederland",
        )
        self._index_postings([internship, java])
        body = self._search("java", location="Amsterdam").json()
        self.assertEqual([item["id"] for item in body["results"]], [java["id"]])
        self.assertEqual(body["matched"], 1)
        self.assertFalse(body["relaxed"])

    def test_every_word_typed_is_required(self):
        """Not any of them: a posting has to say the whole query."""
        both = posting_fixture(
            "arbeitnow:both",
            "Backend Engineer",
            "Wypoon",
            "Python and Kubernetes services at scale.",
        )
        half = posting_fixture(
            "arbeitnow:python-only",
            "Python Engineer",
            "Wypoon",
            "Python services at scale.",
        )
        self._index_postings([both, half])
        body = self._search("python kubernetes").json()
        self.assertEqual([item["id"] for item in body["results"]], [both["id"]])
        self.assertEqual(body["matched"], 1)
        self.assertFalse(body["relaxed"])

    def test_a_word_the_description_carries_is_enough(self):
        """The condition is about the whole posting, not only about its title."""
        self._index_postings(
            [
                posting_fixture(
                    "arbeitnow:body-terraform",
                    "Systems Engineer",
                    "Wypoon",
                    "Own our Terraform modules and the deployment pipeline.",
                )
            ]
        )
        body = self._search("terraform").json()
        self.assertEqual(body["count"], 1)
        # It is a result, but the card's badge stays about the *title*, which does
        # not say it — explained by the caption rather than on the card.
        self.assertEqual(body["results"][0]["matched_terms"], [])

    def test_when_nothing_says_every_word_the_search_loosens_and_says_so(self):
        """A goal sentence is not a keyword, and a dead end would be worse.

        An empty page would be the strict answer, but answering a reasonable query
        with nothing is a worse one. The search loosens to the postings that say
        any of the words — and reports that it did, rather than quietly searching
        for less than it was asked to.
        """
        python = posting_fixture(
            "arbeitnow:python", "Python Engineer", "Wypoon", "Python services at scale."
        )
        terraform = posting_fixture(
            "arbeitnow:terraform",
            "Systems Engineer",
            "Wypoon",
            "Terraform modules at scale.",
        )
        self._index_postings([python, terraform])
        body = self._search("python terraform").json()
        self.assertTrue(body["relaxed"])
        self.assertEqual(body["matched"], 2)
        self.assertEqual(
            {item["id"] for item in body["results"]}, {python["id"], terraform["id"]}
        )

    def test_an_index_built_before_search_text_still_answers_keywords(self):
        """The field is an improvement, not a requirement.

        An index built by an older ingest has no `search_text` in its payloads, and
        its postings have to stay searchable: the words are read from whatever text
        the payload does hold.
        """
        rows = []
        for row in job_feed.rows([PLATFORM]):
            payload = {k: v for k, v in row["payload"].items() if k != "search_text"}
            self.assertNotIn("search_text", payload)
            rows.append((row["record_id"], row["document"], payload))
        vector_store.upsert_records(vector_store.JOBS_COLLECTION, rows)
        body = self._search().json()
        self.assertEqual([item["id"] for item in body["results"]], [PLATFORM["id"]])
        self.assertFalse(body["relaxed"])

    def test_a_filter_word_is_never_a_title_match(self):
        """The other half of the reported bug: the city outranked the language.

        With "java" typed in Amsterdam, the postings whose *titles* said
        "Amsterdam" were ranked first. A filter decides what is eligible; it must
        not also decide the order, or the page rewards a posting for the city it
        sits in.
        """
        city_titled = posting_fixture(
            "arbeitnow:amsterdam-role",
            "Amsterdam Backend Engineer",
            "Canal Systems",
            "We build our services in Java.",
            location="Amsterdam, Netherlands",
        )
        word_titled = posting_fixture(
            "arbeitnow:java-role",
            "Java Back-end Engineer",
            "Wypoon",
            "Build services for our clients.",
            location="Amsterdam, Netherlands",
        )
        self._index_postings([city_titled, word_titled])
        results = self._search("java", location="Amsterdam").json()["results"]
        self.assertEqual([item["id"] for item in results],
                         [word_titled["id"], city_titled["id"]])
        self.assertEqual(results[0]["matched_terms"], ["java"])
        self.assertEqual(
            [word for item in results for word in item["matched_terms"]], ["java"]
        )

    # ── Filters ───────────────────────────────────────────────────────────────
    def test_location_filters_the_whole_collection(self):
        self._index_postings(FILTERED)
        body = self._search(location="Berlin").json()
        self.assertEqual([item["id"] for item in body["results"]], [BERLIN["id"]])
        self.assertEqual(body["matched"], 1)
        self.assertEqual(body["indexed"], len(FILTERED))

    def test_a_location_is_matched_as_a_token_not_a_substring(self):
        """A filter-only browse, so the assertion is about the filter alone."""
        self._index_postings(FILTERED)
        self.assertEqual(self._search("", location="germany").json()["matched"], 2)
        self.assertEqual(self._search("", location="Munchen").json()["matched"], 0)

    def test_a_location_of_remote_also_accepts_the_boards_own_flag(self):
        """The boards say "Remote" in the text and set a flag; either counts."""
        self._index_postings(FILTERED)
        body = self._search(location="remote").json()
        self.assertEqual([item["id"] for item in body["results"]], [UTRECHT["id"]])
        self.assertEqual(body["matched"], 1)

    def test_the_work_arrangement_filter_reads_the_boards_flag(self):
        self._index_postings(FILTERED)
        remote = self._search(remote="true").json()
        self.assertEqual([item["id"] for item in remote["results"]], [UTRECHT["id"]])
        self.assertEqual(remote["matched"], 1)
        # False means "the board did not flag it remote", which is what the page
        # calls "On-site / not stated" — and it still ranks without any query.
        onsite = self._search("", remote="false").json()
        self.assertEqual(onsite["matched"], 3)
        self.assertEqual(onsite["count"], 3)

    def test_experience_buckets_narrow_by_the_wording_the_boards_use(self):
        self._index_postings(FILTERED)
        self.assertEqual(self._search("", experience="internship").json()["matched"], 1)
        self.assertEqual(self._search("", experience="entry").json()["matched"], 1)
        self.assertEqual(self._search("", experience="senior").json()["matched"], 2)
        senior = self._search("", experience="senior").json()
        self.assertEqual(
            {item["id"] for item in senior["results"]}, {BERLIN["id"], UTRECHT["id"]}
        )

    def test_experience_matches_tokens_not_substrings(self):
        """The old client-side rule matched "intern" inside "Internal"."""
        self._index_postings([
            posting_fixture(
                "arbeitnow:internal-tools",
                "Internal Tools Engineer",
                "Loomworks",
                "Maintain the internal tooling and developer platform.",
            )
        ])
        self.assertEqual(self._search(experience="internship").json()["matched"], 0)

    def test_filters_narrow_together(self):
        self._index_postings(FILTERED)
        body = self._search("", location="germany", experience="internship").json()
        self.assertEqual([item["id"] for item in body["results"]], [STUDENT["id"]])
        self.assertEqual(body["matched"], 1)

    def test_matched_counts_the_collection_even_when_the_page_is_small(self):
        """`matched` is about the collection; `count` is about this page.

        Only two of the fixtures say every word of the query — that is what the
        number reports now, and the page shows one of those two.
        """
        self._index_postings(FILTERED)
        body = self._search(limit=1).json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["matched"], 2)
        self.assertEqual(body["indexed"], len(FILTERED))

    def test_filters_that_match_nothing_answer_honestly(self):
        self._index_postings(FILTERED)
        body = self._search(location="Berlin", remote="true").json()
        self.assertTrue(body["available"])
        self.assertEqual(body["matched"], 0)
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["results"], [])
        self.assertEqual(body["indexed"], len(FILTERED))

    def test_a_query_no_posting_mentions_is_a_miss_not_a_loosening(self):
        """An empty page must not also claim its words were loosened.

        `relaxed` means words were dropped *and* rows were found; the page shows
        that notice only beside results, so this never reached a reader — but the
        flag should say what it means. A query the feed does not carry is a plain
        miss, and `matched: 0` already answers it.
        """
        self._index_postings(FILTERED)
        body = self._search("zzzqqq").json()
        self.assertTrue(body["available"])
        self.assertEqual(body["matched"], 0)
        self.assertEqual(body["results"], [])
        self.assertFalse(body["relaxed"])

    def test_without_an_index_the_counts_are_zero_rather_than_invented(self):
        body = self._search(location="Berlin", experience="senior").json()
        self.assertFalse(body["available"])
        self.assertEqual((body["count"], body["matched"], body["indexed"]), (0, 0, 0))

    def test_a_posting_reports_the_boards_own_id_for_it(self):
        """`source_job_id` is the row's identity *there*, beside our `id`."""
        adzuna = posting_fixture(
            "adzuna:5091887331", "Backend Engineer", "Nimbus Labs", "Build the payments API.",
            source="adzuna", source_job_id="5091887331",
        )
        self._index_postings([adzuna])
        result = self._search("backend engineer").json()["results"][0]
        self.assertEqual(result["id"], "adzuna:5091887331")
        self.assertEqual(result["source"], "adzuna")
        self.assertEqual(result["source_job_id"], "5091887331")

    # ── Employment type ───────────────────────────────────────────────────────
    def test_employment_type_narrows_the_whole_collection(self):
        self._index_postings(EMPLOYMENTS)
        for bucket, expected in (
            ("full_time", FULL_TIME_JOB),
            ("part_time", PART_TIME_JOB),
            ("contract", CONTRACT_JOB),
            ("internship", INTERNSHIP),
            ("permanent", FULL_TIME_JOB),
        ):
            with self.subTest(bucket=bucket):
                body = self._search("", employment_type=bucket).json()
                self.assertEqual([item["id"] for item in body["results"]], [expected["id"]])
                self.assertEqual(body["matched"], 1)
                self.assertEqual(body["indexed"], len(EMPLOYMENTS))

    def test_employment_type_matches_the_boards_wording_not_a_lookup(self):
        """The buckets are a translation: Adzuna says "full time", Arbeitnow says
        "part-time" and Himalayas says "Contractor", and all three have to answer.
        """
        self._index_postings(EMPLOYMENTS)
        self.assertEqual(
            self._search("", employment_type="full_time").json()["matched"], 1,
            "Adzuna joins its two halves with a comma",
        )
        self.assertEqual(self._search("", employment_type="contract").json()["matched"], 1)

    def test_an_unknown_employment_bucket_is_refused(self):
        self.assertEqual(self._search(employment_type="gig").status_code, 422)
        self.assertEqual(self._search(employment_type="permanent").status_code, 200)

    def test_the_endpoint_accepts_every_employment_bucket_the_service_offers(self):
        """The route's literal and the rule table must not drift apart."""
        for bucket in job_service.EMPLOYMENT_TYPES:
            with self.subTest(bucket=bucket):
                self.assertEqual(
                    self._search("", employment_type=bucket).status_code, 200
                )

    # ── Posting date ──────────────────────────────────────────────────────────
    def test_posted_within_counts_from_todays_date(self):
        self._index_postings(DATES)
        recent = self._search("", posted_within_days=7).json()
        self.assertEqual([item["id"] for item in recent["results"]], [RECENT["id"]])
        self.assertEqual(recent["matched"], 1)
        self.assertEqual(recent["indexed"], len(DATES))
        self.assertEqual(
            [item["id"] for item in self._search("", posted_within_days=90).json()["results"]],
            [RECENT["id"], OLD["id"]],
            "a wider window reaches the older posting but never the undated one",
        )

    def test_a_posting_no_board_dated_is_never_inside_a_date_filter(self):
        """Absent, not zero: an undated advert must not pass on a technicality.

        The payload simply has no `published_ts` for it, so the range condition
        cannot match — which is the honest reading of "posted this week" when
        nobody said when it was posted.
        """
        self._index_postings(DATES)
        matched = self._search("", posted_within_days=365).json()
        self.assertEqual([item["id"] for item in matched["results"]], [RECENT["id"], OLD["id"]])
        self.assertNotIn(UNDATED["id"], [item["id"] for item in matched["results"]])

    def test_the_new_filters_alone_are_enough_to_search(self):
        """Either of them, on its own, is the filter a browse was asked for."""
        self._index_postings(DATES + EMPLOYMENTS)
        self.assertEqual(self._search("", posted_within_days=7).status_code, 200)
        self.assertEqual(self._search("", employment_type="internship").status_code, 200)

    def test_the_new_filters_narrow_together_with_the_old_ones(self):
        self._index_postings(DATES + EMPLOYMENTS)
        body = self._search(
            "", location="India", employment_type="full_time", posted_within_days=7
        ).json()
        self.assertEqual([item["id"] for item in body["results"]], [RECENT["id"]])
        self.assertEqual(body["matched"], 1)

    # ── Provider status ───────────────────────────────────────────────────────
    def test_the_response_reports_what_each_provider_contributed(self):
        """A feed missing a provider can say which one, and why.

        The ingest writes this beside the collection because only it hears from a
        board that failed: the postings themselves cannot tell "never configured"
        from "had nothing new".
        """
        self._index_postings(FILTERED)
        vector_store.record_meta(
            vector_store.JOBS_COLLECTION,
            {
                "harvested_at": "2026-10-18T10:00:00+00:00",
                "ingested_at": "2026-10-18T10:01:00+00:00",
                "sources": [
                    {"source": "himalayas", "postings": 4, "error": ""},
                    {
                        "source": "adzuna",
                        "postings": 0,
                        "error": "Adzuna is not configured on this server: ADZUNA_APP_ID ...",
                    },
                ],
            },
        )
        body = self._search().json()
        self.assertEqual(
            [(entry["source"], entry["postings"]) for entry in body["sources"]],
            [("himalayas", 4), ("adzuna", 0)],
        )
        self.assertIn("ADZUNA_APP_ID", body["sources"][1]["error"])
        self.assertEqual(body["sources"][0]["error"], "")

    def test_a_credential_the_harvest_recorded_is_not_served(self):
        """A public endpoint does not publish the key of the board that refused it.

        A failed Adzuna request quotes the whole URL, and the key is in its query.
        An index written by such a build — or written before the feed stopped
        recording the query — would otherwise put that key on the same page that
        reports the failed provider. The record is scrubbed on the way out.
        """
        key = "0123456789abcdef0123456789abcdef"
        app_id = "abcdef123456"
        self._index_postings(FILTERED)
        vector_store.record_meta(
            vector_store.JOBS_COLLECTION,
            {
                "harvested_at": "2026-10-18T10:00:00+00:00",
                "ingested_at": "2026-10-18T10:01:00+00:00",
                "sources": [
                    {
                        "source": "adzuna",
                        "postings": 0,
                        "error": (
                            "401 Unauthorized from https://api.adzuna.com/v1/api/jobs/"
                            f"in/search/1?app_id={app_id}&app_key={key}"
                        ),
                    }
                ],
            },
        )
        with mock.patch.dict(os.environ, {"ADZUNA_APP_ID": app_id, "ADZUNA_APP_KEY": key}):
            served = self._search().json()["sources"][0]["error"]
        self.assertNotIn(key, served)
        self.assertNotIn(app_id, served)
        self.assertIn("401", served, "the reader is still told what happened")

    def test_an_index_that_predates_the_record_has_nothing_to_report(self):
        """Empty means "nothing recorded", which a client reads as no notice —
        never as an all-clear that a provider was consulted and answered."""
        self._index_postings(FILTERED)
        vector_store.record_meta(
            vector_store.JOBS_COLLECTION,
            {"harvested_at": "2026-10-18T10:00:00+00:00", "ingested_at": "2026-10-18T10:01:00+00:00"},
        )
        self.assertEqual(self._search().json()["sources"], [])


class JobLocationApiTests(IndexBackedTest):
    """`GET /jobs/locations` — the place vocabulary the Jobs page offers.

    Suggestions used to come from the page's own last results, so a fresh search
    offered nothing and a later one offered only cities it had already returned.
    They are read from the collection now, and every count is the filter's own —
    which is the whole reason the number beside an option is worth trusting. The
    Indian hubs ride along as `preferred`: counted by that same filter, but listed
    even when it counts nothing, because the boards are thin on India and a page
    that answered that with silence would be the least honest part of this.
    """

    def _index_postings(self, postings):
        rows = [
            (row["record_id"], row["document"], row["payload"])
            for row in job_feed.rows(postings)
        ]
        return vector_store.upsert_records(vector_store.JOBS_COLLECTION, rows)

    def _locations(self):
        return client.get("/jobs/locations")

    def _values(self):
        return [option["value"] for option in self._locations().json()["locations"]]

    def _preferred(self):
        return self._locations().json()["preferred"]

    def test_without_an_index_there_are_no_options_rather_than_an_error(self):
        response = self._locations()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"available": False, "locations": [], "preferred": []}
        )

    def test_the_endpoint_needs_no_account(self):
        self._index_postings([BERLIN])
        response = self._locations()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["available"])

    def test_options_are_the_places_the_postings_name(self):
        self._index_postings(FILTERED)
        values = self._values()
        # FILTERED: Berlin/Germany, Utrecht/Netherlands, Munich/Germany, Pune/India.
        for expected in (
            "Germany",
            "Berlin",
            "Utrecht",
            "Netherlands",
            "Munich",
            "Pune",
            "India",
        ):
            self.assertIn(expected, values)

    def test_each_place_is_offered_once(self):
        self._index_postings(FILTERED + [PLATFORM, DESIGNER])  # two of them "Remote"
        values = self._values()
        self.assertEqual(len(values), len(set(values)))

    def test_the_commonest_place_comes_first(self):
        self._index_postings(FILTERED)
        options = self._locations().json()["locations"]
        self.assertEqual(options[0]["value"], "Germany")
        self.assertEqual(options[0]["count"], 2)

    def test_the_count_is_what_searching_that_place_matches(self):
        """The number beside an option has to be the number clicking it returns."""
        self._index_postings(FILTERED + [PLATFORM, DESIGNER, PAID])
        options = self._locations().json()["locations"]
        self.assertTrue(options)
        for option in options:
            with self.subTest(place=option["value"]):
                matched = client.get(
                    "/jobs/search", params={"location": option["value"]}
                ).json()["matched"]
                self.assertEqual(option["count"], matched)

    def test_the_indian_hubs_are_offered_as_preferences_though_no_posting_names_them(self):
        """The feed is European and American; the app is for India.

        Both boards publish into the Indian market thinly, so a hub a candidate
        wants can be missing from the collection entirely. It is listed with its
        real count — zero — rather than dropped, so the page can tell the reader
        what the feed holds at home instead of saying nothing about it.
        """
        self._index_postings([BERLIN])
        preferred = {option["value"]: option["count"] for option in self._preferred()}
        self.assertEqual(list(preferred), list(job_service.PREFERRED_JOB_LOCATIONS))
        self.assertEqual(preferred["India"], 0)
        self.assertEqual(preferred["Bangalore"], 0)
        # And a preference is not smuggled into the live vocabulary: the two lists
        # answer different questions ("what exists" / "what we offer to look for").
        self.assertNotIn("Bangalore", self._values())

    def test_a_preference_the_collection_carries_keeps_its_real_count(self):
        self._index_postings(FILTERED)  # …whose JUNIOR sits at "Pune, India"
        preferred = {option["value"]: option["count"] for option in self._preferred()}
        self.assertEqual(preferred["India"], 1)
        self.assertEqual(preferred["Pune"], 1)
        self.assertEqual(preferred["Hyderabad"], 0)

    def test_every_preference_count_is_what_searching_it_matches(self):
        """A preference makes the same promise as any other option on the page."""
        self._index_postings(FILTERED + [PLATFORM, DESIGNER, PAID])
        for option in self._preferred():
            with self.subTest(place=option["value"]):
                matched = client.get(
                    "/jobs/search", params={"location": option["value"]}
                ).json()["matched"]
                self.assertEqual(option["count"], matched)

    def test_remote_is_one_option_counting_every_way_the_filter_matches_it(self):
        """`Remote` is a place string *and* the boards' flag; the filter takes either."""
        self._index_postings([PLATFORM, DESIGNER, BERLIN])
        options = {
            option["value"]: option["count"]
            for option in self._locations().json()["locations"]
        }
        self.assertEqual(options["Remote"], 2)
        self.assertEqual(options["Berlin"], 1)

    def test_a_numbered_district_is_not_offered_as_a_place(self):
        self._index_postings(
            [
                posting_fixture(
                    "arbeitnow:district",
                    "Data Analyst",
                    "Paris Metrics",
                    "Dashboards and SQL reports.",
                    location="9th arrondissement of Paris, 75009, Paris",
                )
            ]
        )
        self.assertEqual(self._values(), ["Paris"])

    def test_the_list_is_capped_and_ranked_by_count(self):
        postings = [
            posting_fixture(
                f"arbeitnow:town-{index}",
                f"Analyst {index}",
                "Co",
                "Dashboards and SQL reports.",
                location="Tow" + chr(97 + index // 26) + chr(97 + index % 26),
            )
            for index in range(30)
        ]
        # One town is mentioned twice, so it leads the list regardless of the cap.
        postings.append(
            posting_fixture(
                "arbeitnow:town-0-again",
                "Analyst again",
                "Co",
                "Dashboards and SQL reports.",
                location="Towaa",
            )
        )
        self._index_postings(postings)
        options = self._locations().json()["locations"]
        self.assertEqual(len(options), job_service.LOCATION_OPTION_LIMIT)
        self.assertEqual(options[0]["value"], "Towaa")
        self.assertEqual(options[0]["count"], 2)


    def test_a_remote_prefixed_place_is_not_offered_under_a_widened_count(self):
        """A "remote…" place counts every remote posting, so it is not offered.

        `posting_filter` reads any place beginning with "remote" as the boards'
        remote flag too, so "Remote Switzerland" would advertise the whole remote
        feed rather than the Swiss share of it. "Remote" itself stays, and the
        work-arrangement field is where the rest belongs.
        """
        self._index_postings(
            [
                posting_fixture(
                    "arbeitnow:swiss",
                    "Data Analyst",
                    "Alpine Metrics",
                    "Dashboards and SQL reports.",
                    location="Remote Switzerland",
                    remote=True,
                ),
                PLATFORM,  # location "Remote", remote=True
            ]
        )
        options = self._locations().json()["locations"]
        self.assertEqual([option["value"] for option in options], ["Remote"])
        self.assertEqual(options[0]["count"], 2)


class JobFilterUnitTests(unittest.TestCase):
    """`job_service`'s filter vocabulary, without going through the store."""

    def test_nothing_set_means_no_filter(self):
        self.assertIsNone(job_service.posting_filter())

    def test_an_unknown_bucket_is_ignored_rather_than_raising(self):
        """The endpoint's literal is the guard; this stays total either way."""
        self.assertIsNone(job_service.posting_filter(experience="principal"))
        self.assertIsNotNone(job_service.posting_filter(experience="senior"))

    def test_every_offered_bucket_actually_has_rules(self):
        self.assertTrue(job_service.EXPERIENCE_LEVELS, "there is a bucket to filter on")
        for level in job_service.EXPERIENCE_LEVELS:
            built = job_service.posting_filter(experience=level)
            self.assertIsNotNone(built, level)
            self.assertTrue(built.must, level)

    def test_every_offered_employment_bucket_actually_has_rules(self):
        """A bucket a client can ask for must be a bucket the store can answer."""
        self.assertTrue(job_service.EMPLOYMENT_TYPES, "there is a bucket to filter on")
        for bucket in job_service.EMPLOYMENT_TYPES:
            with self.subTest(bucket=bucket):
                built = job_service.posting_filter(employment_type=bucket)
                self.assertIsNotNone(built, bucket)
                self.assertTrue(built.must, bucket)

    def test_an_unknown_employment_bucket_is_ignored_rather_than_raising(self):
        self.assertIsNone(job_service.posting_filter(employment_type="gig"))
        self.assertIsNotNone(job_service.posting_filter(employment_type="permanent"))

    def test_a_date_filter_counts_whole_days_from_midnight(self):
        """So a posting dated exactly `days` ago is not dropped by the clock.

        `published_ts` is the *date* a board gave, so the floor it is compared
        against is a date too: comparing a date against a time of day would make
        the window depend on what hour the search ran at.
        """
        floor = job_service.published_floor(7)
        self.assertEqual(floor % 86400, 0, "midnight, not a moment in the afternoon")
        self.assertEqual(
            (datetime.now(timezone.utc).date() - timedelta(days=7)).isoformat(),
            datetime.fromtimestamp(floor, tz=timezone.utc).date().isoformat(),
        )

    def test_the_ranking_text_falls_back_to_the_filters(self):
        self.assertEqual(job_service.ranking_text("", "Berlin", None, ""), "Berlin")
        self.assertEqual(
            job_service.ranking_text("", "", True, "senior"), "remote senior"
        )
        self.assertEqual(
            job_service.ranking_text("", "", False, ""), "on-site",
            "a filter-only browse must still give the ranker something to rank on",
        )

    def test_a_filter_only_browse_by_employment_type_still_has_words_to_rank_on(self):
        """The bucket is spelled as the words it means, not as the slug: this text
        is embedded and compared by meaning, and an underscore is not a word.
        """
        self.assertEqual(
            job_service.ranking_text("", "", None, "", "full_time"), "full time"
        )
        self.assertEqual(
            job_service.ranking_text("", "", None, "", "permanent"), "permanent"
        )

    def test_a_date_only_browse_still_has_words_to_rank_on(self):
        """The one dimension that names no words gets the phrase that describes it.

        The store refuses an empty query outright, so without this \"newest first\"
        — a filter a candidate can set with nothing else — would answer with an
        empty page. The response echoes the text, so the page never implies a
        search box was filled in.
        """
        self.assertEqual(
            job_service.ranking_text("", "", None, "", "", 7), "recent jobs"
        )
        self.assertEqual(
            job_service.ranking_text("", "India", None, "", "", 7), "India",
            "a filter that does name words still wins",
        )
        self.assertEqual(job_service.ranking_text(), "", "nothing to browse, nothing to rank")

    def test_the_callers_own_words_win(self):
        text = job_service.ranking_text("data analyst", "Berlin", True, "senior")
        self.assertTrue(text.startswith("data analyst"))
        self.assertIn("Berlin", text)

    def test_a_preferred_place_is_a_place_not_a_hub_name(self):
        """`posting_filter` requires *every* word it is handed.

        The questionnaire offers hub names — "Mumbai / Pune", "Delhi / NCR /
        Gurgaon" — and handing one to the store would ask the feed for a single
        posting naming both cities and answer nothing. A preference has to be a
        place the boards could actually have written, so the app's Indian hubs are
        spelled out here one city at a time.
        """
        self.assertTrue(job_service.PREFERRED_JOB_LOCATIONS)
        for value in job_service.PREFERRED_JOB_LOCATIONS:
            with self.subTest(place=value):
                self.assertEqual(value.strip(), value, "trimmed")
                self.assertTrue(value, "no empty place")
                self.assertNotRegex(value, r"[/,;|]", "a hub label, not a place")


class JobTitleMatchTests(unittest.TestCase):
    """The words the ranking lifts a posting on (`job_service.query_terms`)."""

    def test_fillers_and_single_letters_are_dropped(self):
        self.assertEqual(
            job_service.query_terms("a job in the data team"), ["job", "data", "team"]
        )

    def test_words_that_name_a_language_survive_whole(self):
        self.assertEqual(
            job_service.query_terms("C++ and .NET, node.js"),
            ["c++", ".net", "node.js"],
        )

    def test_repeats_are_counted_once_and_order_is_kept(self):
        self.assertEqual(
            job_service.query_terms("Python data python"), ["python", "data"]
        )

    def test_a_title_is_matched_as_tokens_not_substrings(self):
        """Same rule as the experience filter: what the title says on its face."""
        self.assertEqual(
            job_service.title_matches("intern", "Internal Tools Engineer"), []
        )
        self.assertEqual(
            job_service.title_matches("engineer python", "Python Engineer"),
            ["engineer", "python"],
        )

    def test_no_query_means_nothing_to_match_on(self):
        self.assertEqual(job_service.query_terms("  "), [])


class JobKeywordTests(unittest.TestCase):
    """The keyword rule (`job_service.matches_token`) — what counts as saying a word.

    Whole words, with the two allowances a job board needs and the one refusal it
    needs more: "developer" has to find "Developers" and "node" has to find
    "Node.js", while "java" must not find JavaScript.
    """

    def test_a_whole_word_counts(self):
        self.assertTrue(job_service.matches_token("java", "java"))

    def test_a_plural_of_the_word_counts(self):
        self.assertTrue(job_service.matches_token("developer", "developers"))
        self.assertTrue(job_service.matches_token("technician", "technicians"))

    def test_a_compound_the_word_introduces_counts(self):
        self.assertTrue(job_service.matches_token("node", "node.js"))
        self.assertTrue(job_service.matches_token("front", "front-end"))

    def test_a_longer_word_that_merely_starts_the_same_does_not(self):
        self.assertFalse(job_service.matches_token("java", "javascript"))
        self.assertFalse(job_service.matches_token("data", "database"))
        self.assertFalse(job_service.matches_token("intern", "internal"))

    def test_a_posting_is_read_as_lower_case_words(self):
        """The boards mix their cases; the rule must not care."""
        words = job_service.posting_words({"title": "Senior Python Engineer"})
        self.assertIn("python", words)
        self.assertNotIn("Python", words)

    def test_the_body_counts_as_well_as_the_title(self):
        words = job_service.posting_words(
            {"title": "Engineer", "excerpt": "Terraform modules."}
        )
        self.assertTrue(job_service.mentions(words, "terraform"))

    def test_the_rule_requires_every_word_and_loosens_to_any(self):
        candidates = [
            {"id": "a", "title": "Python Engineer", "excerpt": "Python and Kubernetes."},
            {"id": "b", "title": "Python Developer", "excerpt": "Python only."},
        ]
        kept, relaxed = job_service._narrow(candidates, ["python", "kubernetes"])
        self.assertEqual([payload["id"] for payload in kept], ["a"])
        self.assertFalse(relaxed)

        kept, relaxed = job_service._narrow(candidates, ["python", "terraform"])
        self.assertEqual(sorted(payload["id"] for payload in kept), ["a", "b"])
        self.assertTrue(relaxed)

    def test_no_words_keep_everything(self):
        candidates = [{"id": "a", "title": "Anything"}]
        self.assertEqual(job_service._narrow(candidates, []), (candidates, False))

    def test_a_query_nothing_mentions_is_a_miss_not_a_loosening(self):
        """`relaxed` means words were dropped *and* rows were found.

        A query the feed does not carry at all used to come back `relaxed: true`
        with no rows — "we loosened, and even that found nothing" — which is a
        loosening that never happened. The flag is the page's notice that something
        less than it asked for is on screen; with nothing on screen there is
        nothing to excuse.
        """
        candidates = [{"id": "a", "title": "Python Engineer", "excerpt": "Python only."}]
        self.assertEqual(job_service._narrow(candidates, ["cobol"]), ([], False))


class JobRankTests(unittest.TestCase):
    """`job_service._rank` — what turns near-hits into something a search box returns.

    Called directly with synthetic scores, so the rule is tested without depending
    on how good (or bad) the configured embedder happens to be.
    """

    def test_a_posting_that_never_names_the_query_falls_below_one_that_does(self):
        """The shape the live index shows: a listing in front that never says it.

        For "python" the store puts a German facilities-maintenance listing second,
        ahead of postings that actually name the language. Meaning alone cannot
        fix that; saying the word can.
        """
        hits = [
            (
                0.55,
                {
                    "id": "silent",
                    "title": "Technischer Anlagenbetreuer",
                    "company": "Hauswerk",
                    "excerpt": "Wartung der Lüftungs- und Gebäudetechnik.",
                },
            ),
            (
                0.21,
                {
                    "id": "mentions",
                    "title": "Backend Engineer",
                    "company": "Wypoon",
                    "excerpt": "You will write Python services and own their deployment.",
                },
            ),
        ]
        ranked = job_service._rank(hits, "python", 10)
        self.assertEqual(
            [payload["id"] for _, _, payload in ranked], ["mentions", "silent"]
        )

    def test_the_title_outranks_a_mention(self):
        hits = [
            (
                0.55,
                {
                    "id": "mentions",
                    "title": "Backend Engineer",
                    "company": "Wypoon",
                    "excerpt": "You will write Python services.",
                },
            ),
            (
                0.21,
                {
                    "id": "titled",
                    "title": "Python Engineer",
                    "company": "Wypoon",
                    "excerpt": "Own our back-end services.",
                },
            ),
        ]
        ranked = job_service._rank(hits, "python", 10)
        self.assertEqual(
            [payload["id"] for _, _, payload in ranked], ["titled", "mentions"]
        )

    def test_more_of_the_query_in_the_title_wins(self):
        hits = [
            (
                0.90,
                {"id": "one", "title": "Data Engineer", "company": "", "excerpt": ""},
            ),
            (
                0.10,
                {
                    "id": "two",
                    "title": "Data Analyst Engineer",
                    "company": "",
                    "excerpt": "",
                },
            ),
        ]
        ranked = job_service._rank(hits, "data analyst engineer", 10)
        self.assertEqual([payload["id"] for _, _, payload in ranked], ["two", "one"])

    def test_a_query_nothing_carries_keeps_the_stores_order(self):
        hits = [
            (0.55, {"id": "first", "title": "Facilities Technician", "excerpt": ""}),
            (0.21, {"id": "second", "title": "Backend Engineer", "excerpt": ""}),
        ]
        ranked = job_service._rank(hits, "cobol", 10)
        self.assertEqual([payload["id"] for _, _, payload in ranked], ["first", "second"])

    def test_the_page_is_cut_to_the_limit_after_the_resort(self):
        hits = [
            (0.90, {"id": "quiet", "title": "Facilities Technician", "excerpt": ""}),
            (0.10, {"id": "named", "title": "Python Engineer", "excerpt": ""}),
        ]
        ranked = job_service._rank(hits, "python", 1)
        self.assertEqual([payload["id"] for _, _, payload in ranked], ["named"])


def catalog_role(title: str) -> dict:
    """A real catalogued role, straight from the database the endpoint reads."""
    for role in career_service.get_all_roles():
        if role["title"].lower() == title.lower():
            return role
    raise AssertionError(f"no catalogued role titled {title!r}")


class RoleJobsApiTests(IndexBackedTest):
    """`POST /jobs/for-role` — the read behind "live openings" on a role card.

    What this pins down:

    * a role that does not exist is a 404, not an empty list;
    * the postings returned are the ones nearest *that role*, from the job
      collection only;
    * the questionnaire joins the role in the query, and is optional;
    * no index still answers honestly (`available: false`), and no account is
      needed.
    """

    def _index_postings(self, postings):
        rows = [
            (row["record_id"], row["document"], row["payload"])
            for row in job_feed.rows(postings)
        ]
        return vector_store.upsert_records(vector_store.JOBS_COLLECTION, rows)

    def _for_role(self, role_id, **payload):
        return client.post("/jobs/for-role", json={"role_id": role_id, **payload})

    def test_without_an_index_the_endpoint_says_so_instead_of_erroring(self):
        role = catalog_role("Platform Engineer")
        response = self._for_role(role["id"])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["role_id"], role["id"])
        self.assertEqual(body["role_title"], role["title"])
        self.assertFalse(body["available"])
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["results"], [])

    def test_an_unknown_role_is_a_404(self):
        self.assertEqual(self._for_role("not_a_role").status_code, 404)

    def test_the_postings_nearest_the_role_win(self):
        role = catalog_role("Platform Engineer")
        self._index_postings([DESIGNER, PLATFORM])
        body = self._for_role(role["id"]).json()
        self.assertTrue(body["available"])
        self.assertEqual(body["results"][0]["id"], PLATFORM["id"])

    def test_a_posting_carries_everything_a_link_needs(self):
        role = catalog_role("Platform Engineer")
        self._index_postings([PLATFORM])
        item = self._for_role(role["id"], limit=1).json()["results"][0]
        self.assertEqual(item["url"], PLATFORM["url"])
        self.assertEqual(item["source"], PLATFORM["source"])
        self.assertTrue(item["company"])

    def test_role_openings_rank_by_meaning_with_no_title_boost(self):
        """A role query is a whole questionnaire, not a search box.

        Its words are the catalog's own, so lifting a title that happens to carry
        one of them would re-order postings on evidence nobody typed. The field
        comes back empty, and the ordering is the index's.
        """
        role = catalog_role("Platform Engineer")
        self._index_postings([PLATFORM, DESIGNER])
        results = self._for_role(role["id"]).json()["results"]
        self.assertTrue(results)
        for item in results:
            self.assertEqual(item["matched_terms"], [])
        self.assertEqual(results[0]["id"], PLATFORM["id"])

    def test_the_questionnaire_joins_the_role_in_the_query(self):
        role = catalog_role("Platform Engineer")
        text = job_service.role_query(
            role,
            {
                "interests": ["Data visualisation"],
                "current_skills": ["Figma"],
                "career_goal": "design systems",
                "location": "Pune",
            },
        )
        self.assertIn(role["title"], text)
        for value in ("Data visualisation", "Figma", "design systems", "Pune"):
            self.assertIn(value, text)

    def test_without_a_questionnaire_the_query_is_just_the_role(self):
        role = catalog_role("Platform Engineer")
        text = job_service.role_query(role)
        self.assertIn(role["title"], text)
        self.assertNotIn("Figma", text)

    def test_the_profile_is_optional_and_the_limit_is_bounded(self):
        role = catalog_role("Platform Engineer")
        self._index_postings([PLATFORM, DESIGNER])
        self.assertEqual(self._for_role(role["id"], limit=1).json()["count"], 1)
        self.assertEqual(self._for_role(role["id"], limit=2).json()["count"], 2)
        self.assertEqual(self._for_role(role["id"], limit=0).status_code, 422)
        self.assertEqual(self._for_role(role["id"], limit=1000).status_code, 422)
        self.assertEqual(self._for_role("").status_code, 422)

    def test_the_endpoint_needs_no_account(self):
        role = catalog_role("Platform Engineer")
        self.assertEqual(self._for_role(role["id"]).status_code, 200)


# ── AI classification ─────────────────────────────────────────────────────────
#: Adverts long enough to classify (a title-only posting is *never* classified — see
#: `classification.MIN_DESCRIPTION_CHARS`), each describing a different kind of job so
#: that the category filter has something to tell apart.
JAVA_ADVERT = (
    "Build and run payment services in Java and Spring Boot. Design REST APIs, own the "
    "SQL data models, and deploy to a Kubernetes platform. Must have 3+ years of Java, "
    "strong SQL. Nice to have: fintech exposure."
)
SRE_ADVERT = (
    "Own our Kubernetes platform and Terraform modules. Run the production clusters, "
    "improve the deployment pipelines, and lead on observability and incident response. "
    "Must have production on-call experience with Linux."
)
JAVA_POSTING = posting_fixture(
    "adzuna:java-backend", "Backend Developer", "Deccan Cloud", JAVA_ADVERT,
    location="Pune, India",
)
SRE_POSTING = posting_fixture(
    "himalayas:platform-sre", "Site Reliability Engineer", "Nimbus Labs", SRE_ADVERT,
    location="Bengaluru, India",
)
TITLE_ONLY_POSTING = posting_fixture(
    "arbeitnow:title-only", "Senior Backend Engineer", "Rhine Cloud", "Apply now.",
    location="Bonn, Germany",
)


def index_postings(postings) -> int:
    """Puts fixtures into the throwaway `job_role` collection."""
    rows = [
        (row["record_id"], row["document"], row["payload"]) for row in job_feed.rows(postings)
    ]
    return vector_store.upsert_records(vector_store.JOBS_COLLECTION, rows)


class JobClassifyApiTests(IndexBackedTest):
    """`POST /jobs/classify` — the one job endpoint that spends anything.

    What this pins down: the verdict is the stored one whether or not the model was
    reached, a listing the classifier cannot place is answered as Unclassified rather
    than failed, a missing key or a missing index is the deployment's problem and says
    so, and the AI budget is charged only when a model call is actually about to
    happen — which is why reading a verdict (or reading an advert that says too little
    to classify) is free.
    """

    def setUp(self):
        super().setUp()
        clear_store()
        self._original_max = dependencies.ai_limiter.max_calls
        self.addCleanup(self._reset_budget)

    def _reset_budget(self):
        dependencies.ai_limiter.max_calls = self._original_max
        dependencies.ai_limiter.reset()

    def _set_budget(self, calls: int):
        """Gives this test the whole AI budget, so spending can be counted exactly."""
        dependencies.ai_limiter.max_calls = calls
        dependencies.ai_limiter.reset()

    def _classify(self, listing_id: str, **body):
        return client.post("/jobs/classify", json={"id": listing_id, **body})

    def test_without_an_index_it_says_which_command_builds_one(self):
        response = self._classify("adzuna:java-backend")
        self.assertEqual(response.status_code, 503)
        self.assertIn("ingest_jobs", response.json()["detail"])

    def test_an_unknown_listing_is_a_404(self):
        index_postings([JAVA_POSTING])
        self.assertEqual(self._classify("adzuna:nobody").status_code, 404)

    def test_without_a_key_it_says_so_instead_of_blaming_the_advert(self):
        index_postings([JAVA_POSTING])
        with mock.patch.object(ai_service, "api_key", ""):
            response = self._classify("adzuna:java-backend")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Gemini API key", response.json()["detail"])

    def test_a_listing_comes_back_with_what_the_job_actually_is(self):
        index_postings([JAVA_POSTING])
        with using(fake_model(answer())):
            response = self._classify("adzuna:java-backend")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["canonical_role"], "Backend Development")
        self.assertEqual(body["primary_category"], "Development")
        self.assertEqual(body["required_skills"], ["Java", "Spring Boot", "SQL"])
        self.assertEqual(body["listing_id"], "adzuna:java-backend")
        self.assertFalse(body["cached"])

    def test_a_listing_already_classified_is_read_without_any_ai_at_all(self):
        """The store is the whole point: a page full of classified cards needs no key
        and no quota, so it keeps working on a deployment whose key has run out."""
        index_postings([JAVA_POSTING])
        with using(fake_model(answer())):
            self._classify("adzuna:java-backend")
        with mock.patch.object(ai_service, "api_key", ""):
            response = self._classify("adzuna:java-backend")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["cached"])

    def test_reading_a_verdict_costs_nothing_but_asking_for_one_is_metered(self):
        index_postings([JAVA_POSTING])
        self._set_budget(1)
        with using(fake_model(answer())):
            first = self._classify("adzuna:java-backend")
            second = self._classify("adzuna:java-backend")
            forced = self._classify("adzuna:java-backend", force=True)
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["cached"])
        # The budget was spent above, so a second *charge* would be a 429.
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["cached"])
        self.assertEqual(forced.status_code, 429)

    def test_an_advert_too_thin_to_classify_costs_no_budget_either(self):
        index_postings([TITLE_ONLY_POSTING, JAVA_POSTING])
        self._set_budget(1)
        with using(fake_model(answer())):
            thin = self._classify("arbeitnow:title-only")
            listed = self._classify("adzuna:java-backend")
        self.assertEqual(thin.status_code, 200)
        self.assertEqual(thin.json()["canonical_role"], "Unclassified")
        self.assertIn("does not describe the job", thin.json()["unclassified_reason"])
        # It reached no model, so the one token was still there for the listing that
        # did need reading.
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["canonical_role"], "Backend Development")

    def test_an_unreadable_answer_is_reported_rather_than_failed(self):
        index_postings([JAVA_POSTING])
        with using(fake_model(text="I am afraid I cannot do that.")):
            response = self._classify("adzuna:java-backend")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["canonical_role"], "Unclassified")
        self.assertEqual(response.json()["unclassified_kind"], "unreadable")


class JobClassificationSearchTests(IndexBackedTest):
    """What a *read* of the feed says about the verdicts it holds."""

    def setUp(self):
        super().setUp()
        clear_store()

    def _classify(self, listing_id: str, stated: dict):
        with using(fake_model(stated)):
            response = client.post("/jobs/classify", json={"id": listing_id})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _search(self, **params):
        return client.get("/jobs/search", params=params)

    def test_a_result_carries_its_verdict_rather_than_a_guess(self):
        index_postings([JAVA_POSTING])
        self._classify("adzuna:java-backend", answer())
        body = self._search(q="java", limit=10).json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["classification"]["canonical_role"], "Backend Development")
        self.assertTrue(body["results"][0]["classification"]["cached"])
        self.assertEqual(body["classified"], 1)

    def test_a_result_nobody_has_read_says_so_with_a_null(self):
        index_postings([JAVA_POSTING])
        body = self._search(q="java").json()
        self.assertIsNone(body["results"][0]["classification"])
        self.assertEqual(body["classified"], 0)

    def test_the_category_filter_narrows_to_a_filed_listing(self):
        index_postings([JAVA_POSTING, SRE_POSTING])
        self._classify("adzuna:java-backend", answer())
        self._classify(
            "himalayas:platform-sre",
            answer(
                canonical_role="Site Reliability Engineering",
                primary_category="Infrastructure & Cloud",
                required_skills=["Kubernetes", "Terraform"],
            ),
        )
        body = self._search(category="Infrastructure & Cloud", limit=10).json()
        titles = [row["title"] for row in body["results"]]
        self.assertEqual(titles, ["Site Reliability Engineer"])
        self.assertEqual(body["matched"], 1)
        self.assertEqual(body["classified"], 2)

    def test_a_listing_nobody_has_classified_matches_no_category(self):
        index_postings([JAVA_POSTING])
        body = self._search(category="Development").json()
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["matched"], 0)
        self.assertTrue(body["available"])

    def test_a_category_alone_is_enough_to_search(self):
        index_postings([JAVA_POSTING])
        self._classify("adzuna:java-backend", answer())
        response = self._search(category="Development")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Development", response.json()["query"])

    def test_an_unknown_category_is_refused_with_the_vocabulary(self):
        response = self._search(category="Quantum Engineering")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Other / Unclassified", response.json()["detail"])

    def test_the_unclassified_bucket_is_a_category_not_a_leftover_bin(self):
        """A thin advert is filed under "Other / Unclassified" because the classifier
        *said so* — and a listing nobody has read is not."""
        index_postings([TITLE_ONLY_POSTING, JAVA_POSTING])
        with using(fake_model(answer())):
            client.post("/jobs/classify", json={"id": "arbeitnow:title-only"})
        body = self._search(category="Other / Unclassified", limit=10).json()
        self.assertEqual([row["title"] for row in body["results"]], ["Senior Backend Engineer"])
        self.assertEqual(body["matched"], 1)
        # The Java advert has no verdict at all, so no category of any kind holds it.
        self.assertEqual(self._search(category="Development").json()["matched"], 0)


if __name__ == "__main__":
    unittest.main()
