"""The `/jobs/search` endpoint — the read path over the live postings.

What this pins down:

* the endpoint is public, like `/roles`, and needs no account;
* results come from the `job_role` collection and never from the curated role
  index sitting beside it in the same store;
* ranking is semantic, so the platform posting wins for a platform query;
* with no index built, the endpoint still answers honestly (`available: false`)
  rather than erroring or inventing a weaker search;
* the inputs are validated, so a client cannot ask for everything at once.

Isolation (throwaway database and vector index) comes from `tests.harness`; the
posting fixtures are shared with `test_job_feed`.
"""
import unittest

from tests.harness import IndexBackedTest, client  # noqa: F401  (isolation first)
from tests.test_job_feed import DESIGNER, PLATFORM, posting_fixture, role_fixture  # noqa: E402

from services import job_feed, vector_store  # noqa: E402

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

    def test_results_are_the_nearest_postings(self):
        self._index_postings([PLATFORM, DESIGNER])
        body = self._search().json()
        self.assertTrue(body["available"])
        self.assertEqual(body["count"], 2)
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
        self._index_postings([PLATFORM, DESIGNER])
        self.assertEqual(self._search(limit=1).json()["count"], 1)
        self.assertEqual(self._search(limit=2).json()["count"], 2)
        self.assertEqual(self._search(limit=0).status_code, 422)
        self.assertEqual(self._search(limit=1000).status_code, 422)

    def test_a_query_is_required(self):
        self.assertEqual(client.get("/jobs/search").status_code, 422)
        self.assertEqual(client.get("/jobs/search", params={"q": ""}).status_code, 422)

    def test_the_endpoint_needs_no_account(self):
        """Nothing in this file sends an Authorization header."""
        self.assertEqual(self._search().status_code, 200)


if __name__ == "__main__":
    unittest.main()
