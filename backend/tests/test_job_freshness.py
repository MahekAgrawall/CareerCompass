"""Harvest freshness — when the live postings were pulled, and how old that is.

The gap these tests close: nothing used to record when the postings were
harvested, so an index built a month ago looked exactly like one built this
morning, and a candidate had no way to tell that what they were reading had been
overtaken by the boards. The contract:

* the artifact records its own harvest time, and re-ingesting it reports *that*
  date rather than today's;
* the ingest writes the harvest and ingest times beside the collection;
* `/jobs/search` reports the age, and `/health` reports it too so a monitor can
  see a feed going stale without running a search;
* a missing or unparseable date is reported as unknown, never invented;
* `--if-stale` makes a frequent schedule cheap: it is a no-op while the feed is
  young and never touches the collection to decide that.

Isolation (throwaway database and index) comes from `tests.harness`; the posting
fixtures are shared with `test_job_feed` and `test_job_api`.
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from tests.harness import IndexBackedTest, client  # noqa: F401  (isolation first)
from tests.test_job_feed import DESIGNER, PLATFORM  # noqa: E402

from scripts import ingest_jobs  # noqa: E402
from services import job_feed, job_service, vector_store  # noqa: E402


def days_ago(days: int) -> str:
    """A harvest stamp `days` whole days in the past, in the artifact's format."""
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return moment.isoformat(timespec="seconds")


class ArtifactTests(unittest.TestCase):
    """`job_feed.save`/`load_artifact` — the stamp travels with the data."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="careercompass_freshness_")
        self.addCleanup(shutil.rmtree, self._tmp, True)
        self.path = os.path.join(self._tmp, "job_postings.json")

    def test_saving_stamps_when_the_postings_were_pulled(self):
        job_feed.save([PLATFORM, DESIGNER], self.path)
        artifact = job_feed.load_artifact(self.path)
        self.assertEqual(artifact["postings"], [PLATFORM, DESIGNER])
        stamp = datetime.fromisoformat(artifact["harvested_at"])
        self.assertIsNotNone(stamp.tzinfo, "the stamp is timezone-aware, not naive")
        self.assertLess(abs((datetime.now(timezone.utc) - stamp).total_seconds()), 60)

    def test_an_observed_harvest_time_is_kept_exactly_as_given(self):
        """A re-ingest must be able to say what the file says, not what time it is."""
        observed = "2026-01-02T03:04:05+00:00"
        job_feed.save([PLATFORM], self.path, harvested_at=observed)
        self.assertEqual(job_feed.load_artifact(self.path)["harvested_at"], observed)
        self.assertEqual(job_feed.load(self.path), [PLATFORM])

    def test_a_bare_list_from_an_older_version_still_loads(self):
        """The format changed; the files on disk did not have to."""
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump([PLATFORM], handle)
        artifact = job_feed.load_artifact(self.path)
        self.assertEqual(artifact["postings"], [PLATFORM])
        self.assertEqual(
            artifact["harvested_at"], "", "no date is recorded, rather than today's"
        )
        self.assertEqual(artifact["sources"], [], "no board record either")
        self.assertEqual(job_feed.load(self.path), [PLATFORM])

    def test_a_saved_harvest_records_what_each_board_did(self):
        """The board record travels in the file, so `--from-file` keeps it.

        Only the harvest hears from a board that failed, and a re-ingest of the
        file has no network on which to hear it again — so "Adzuna was never
        configured" has to be written down beside the postings, not looked up.
        """
        status = [
            {"source": "himalayas", "postings": 2, "error": ""},
            {
                "source": "adzuna",
                "postings": 0,
                "error": "Adzuna is not configured on this server: ADZUNA_APP_ID ...",
            },
        ]
        job_feed.save([PLATFORM, DESIGNER], self.path, sources=status)
        artifact = job_feed.load_artifact(self.path)
        self.assertEqual(artifact["sources"], status)
        self.assertEqual(job_feed.load(self.path), [PLATFORM, DESIGNER])

    def test_a_harvest_saved_without_a_board_record_reloads_without_one(self):
        """No record reads back as nothing recorded, never as an all-clear."""
        job_feed.save([PLATFORM], self.path)
        self.assertEqual(job_feed.load_artifact(self.path)["sources"], [])

    def test_the_harvest_stamp_is_utc_iso_8601(self):
        self.assertRegex(
            job_feed.harvest_stamp(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$"
        )


class FreshnessReadingTests(unittest.TestCase):
    """`job_service.freshness`'s reading of a sidecar, without a store."""

    def test_nothing_recorded_is_reported_as_unknown(self):
        state = job_service.freshness({})
        self.assertEqual(state["harvested_at"], "")
        self.assertIsNone(state["age_days"])
        self.assertFalse(state["stale"])
        self.assertEqual(state["stale_after_days"], job_service.STALE_AFTER_DAYS)

    def test_the_age_is_whole_days_and_only_ever_positive(self):
        self.assertEqual(job_service.age_days(days_ago(3)), 3)
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(timespec="seconds")
        self.assertEqual(job_service.age_days(future), 0, "a clock skew is not a negative age")

    def test_a_date_that_cannot_be_parsed_is_unknown_not_a_crash(self):
        for value in ("", "sometime last week", "2026-13-40"):
            self.assertIsNone(job_service.age_days(value), value)
        state = job_service.freshness({"harvested_at": "sometime last week"})
        self.assertIsNone(state["age_days"])
        self.assertFalse(state["stale"])

    def test_the_threshold_is_where_staleness_begins(self):
        threshold = job_service.STALE_AFTER_DAYS
        just_under = job_service.freshness({"harvested_at": days_ago(threshold - 1)})
        at_threshold = job_service.freshness({"harvested_at": days_ago(threshold)})
        self.assertFalse(just_under["stale"])
        self.assertTrue(at_threshold["stale"])


class IngestFreshnessTests(IndexBackedTest):
    """The ingest records the provenance, and the API reports it back."""

    def _artifact(self, postings, harvested_at=""):
        path = os.path.join(self._tmp, "job_postings.json")
        job_feed.save(postings, path, harvested_at=harvested_at)
        return path

    def _ingest(self, postings, harvested_at=""):
        with contextlib.redirect_stdout(io.StringIO()):
            return ingest_jobs.ingest(
                from_file=self._artifact(postings, harvested_at), save_path=""
            )

    def _run(self, *args):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = ingest_jobs.main(list(args))
        return code, buffer.getvalue()

    def _index_postings(self, postings):
        rows = [
            (row["record_id"], row["document"], row["payload"])
            for row in job_feed.rows(postings)
        ]
        return vector_store.upsert_records(vector_store.JOBS_COLLECTION, rows)

    def test_the_ingest_records_both_dates_beside_the_collection(self):
        result = self._ingest([PLATFORM])
        meta = vector_store.recorded_meta(vector_store.JOBS_COLLECTION)
        self.assertEqual(meta["harvested_at"], result["status"]["harvested_at"])
        self.assertTrue(meta["ingested_at"])
        self.assertEqual(
            job_service.freshness()["harvested_at"], result["status"]["harvested_at"]
        )

    def test_a_board_that_could_not_be_read_survives_a_file_reingest(self):
        """`--from-file` reports the harvest's own board record, not just its rows.

        An index built from a saved file used to be able to name only the boards
        its rows came from, so a server with no Adzuna key showed an Indian-less
        feed and said nothing about why — the one case the `sources` block exists
        for. The record was heard during the harvest and written into the file, so
        it is there to be re-ingested.
        """
        path = os.path.join(self._tmp, "job_postings.json")
        job_feed.save(
            [PLATFORM],
            path,
            sources=[
                {"source": "arbeitnow", "postings": 1, "error": ""},
                {
                    "source": "adzuna",
                    "postings": 0,
                    "error": "Adzuna is not configured on this server: ADZUNA_APP_ID must be set.",
                },
            ],
        )
        with contextlib.redirect_stdout(io.StringIO()):
            ingest_jobs.ingest(from_file=path, save_path="")
        recorded = vector_store.recorded_meta(vector_store.JOBS_COLLECTION)["sources"]
        self.assertEqual([entry["source"] for entry in recorded], ["arbeitnow", "adzuna"])
        self.assertIn("ADZUNA_APP_ID", recorded[1]["error"])
        body = client.get("/jobs/search", params={"q": "platform"}).json()
        self.assertIn("ADZUNA_APP_ID", body["sources"][1]["error"])

    def test_a_file_reingest_without_a_board_record_still_names_its_boards(self):
        """An artifact from before the record existed reports what its rows say.

        The fallback is not silent: the boards that are in the file are counted, so
        an older file loses only the boards that failed to reach it.
        """
        self._ingest([PLATFORM, DESIGNER])
        recorded = vector_store.recorded_meta(vector_store.JOBS_COLLECTION)["sources"]
        self.assertEqual([(entry["source"], entry["postings"]) for entry in recorded], [("arbeitnow", 2)])

    def test_reingesting_an_old_artifact_reports_the_artifacts_date_not_today(self):
        self._ingest([PLATFORM], harvested_at=days_ago(21))
        state = job_service.freshness()
        self.assertEqual(state["age_days"], 21)
        self.assertTrue(state["stale"])

    def test_the_search_response_carries_the_freshness(self):
        self._ingest([PLATFORM], harvested_at=days_ago(2))
        body = client.get("/jobs/search", params={"q": "platform"}).json()
        self.assertEqual(body["freshness"]["age_days"], 2)
        self.assertFalse(body["freshness"]["stale"])
        self.assertEqual(body["freshness"]["stale_after_days"], job_service.STALE_AFTER_DAYS)

    def test_a_stale_harvest_is_flagged_on_the_search_response(self):
        self._ingest([PLATFORM], harvested_at=days_ago(job_service.STALE_AFTER_DAYS + 5))
        body = client.get("/jobs/search", params={"q": "platform"}).json()
        self.assertTrue(body["freshness"]["stale"])

    def test_without_a_recorded_harvest_the_response_says_unknown(self):
        """An index built by hand, or on a Qdrant server, has no sidecar to read."""
        self._index_postings([PLATFORM])
        body = client.get("/jobs/search", params={"q": "platform"}).json()
        self.assertTrue(body["available"])
        self.assertEqual(body["freshness"]["harvested_at"], "")
        self.assertIsNone(body["freshness"]["age_days"])
        self.assertFalse(body["freshness"]["stale"])

    def test_health_reports_the_job_freshness(self):
        """The signal a scheduled re-ingest (or an alert) can be built on."""
        self._ingest([PLATFORM], harvested_at=days_ago(30))
        body = client.get("/health").json()
        self.assertTrue(body["job_postings"]["stale"])
        self.assertEqual(body["job_postings"]["stale_after_days"], job_service.STALE_AFTER_DAYS)

    # ── --if-stale: what makes a frequent schedule cheap ──────────────────────
    def test_if_stale_skips_a_run_while_the_feed_is_young(self):
        self._ingest([PLATFORM], harvested_at=days_ago(1))
        fresh = self._artifact([DESIGNER])
        code, out = self._run("--from-file", fresh, "--save", "", "--if-stale", "14")
        self.assertEqual(code, 0)
        self.assertIn("skipped", out)
        # A no-op that still wrote something would not be a no-op: the second
        # harvest must not have landed.
        self.assertEqual(vector_store.count_points(vector_store.JOBS_COLLECTION), 1)
        hits = vector_store.search_records(vector_store.JOBS_COLLECTION, "design", limit=5)
        self.assertEqual([payload["id"] for _, payload in hits], [PLATFORM["id"]])

    def test_if_stale_runs_once_the_feed_has_aged(self):
        self._ingest([PLATFORM], harvested_at=days_ago(21))
        aged = self._artifact([DESIGNER])
        code, out = self._run("--from-file", aged, "--save", "", "--if-stale", "14")
        self.assertEqual(code, 0)
        self.assertNotIn("skipped", out)
        self.assertEqual(vector_store.count_points(vector_store.JOBS_COLLECTION), 2)

    def test_rebuild_overrides_if_stale(self):
        self._ingest([PLATFORM], harvested_at=days_ago(1))
        again = self._artifact([PLATFORM])
        code, out = self._run(
            "--from-file", again, "--save", "", "--rebuild", "--if-stale", "14"
        )
        self.assertEqual(code, 0)
        self.assertNotIn("skipped", out)
        self.assertEqual(vector_store.count_points(vector_store.JOBS_COLLECTION), 1)

    def test_with_nothing_recorded_a_run_is_due(self):
        """`--if-stale` must never be the reason a first harvest is skipped."""
        code, out = self._run(
            "--from-file", self._artifact([DESIGNER]), "--save", "", "--if-stale", "14"
        )
        self.assertEqual(code, 0)
        self.assertNotIn("skipped", out)
        self.assertEqual(vector_store.count_points(vector_store.JOBS_COLLECTION), 1)


if __name__ == "__main__":
    unittest.main()
