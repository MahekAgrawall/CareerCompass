"""Role-catalog tests: content contract, matching reachability and catalog upgrades.

`data/roles.json` is the single source of truth for the catalog, and
`init_db()` syncs it into SQLite on every startup. These tests guard three
things that are easy to break by hand-editing the JSON:

1. **content contract** — every role carries the full set of fields the UI reads;
2. **reachability** — every role can actually be reached by the matching engine
   from a real questionnaire answer (an unreachable role is invisible in the app);
3. **upgrade path** — a database created before the catalog grew picks up the new
   roles without losing a candidate's saved roadmaps or tracker topics.
"""
import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.harness import client  # noqa: E402,F401  (points the live DB at a throwaway file)

from config import INTEREST_OPTIONS, SKILL_OPTIONS  # noqa: E402
from database import db  # noqa: E402
from services import career_service  # noqa: E402

# Any one role that has shipped since the first release, used as the "old catalog".
LEGACY_ROLE_ID = "backend_dev"


def load_catalog():
    with open(db.ROLES_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["roles"]


class CatalogContentTests(unittest.TestCase):
    def setUp(self):
        self.roles = load_catalog()

    def test_catalog_is_within_the_target_size(self):
        self.assertGreaterEqual(len(self.roles), 90, "the catalog should offer a broad set of roles")
        self.assertLessEqual(
            len(self.roles), 130,
            "past ~130 roles the directory stops being scannable and belongs behind search, "
            "not one long list — the semantic index is what keeps the big catalog useful",
        )

    def test_role_ids_are_unique(self):
        ids = [r["id"] for r in self.roles]
        self.assertEqual(len(ids), len(set(ids)), "duplicate role ids would collide on the primary key")

    def test_every_role_carries_the_full_content_contract(self):
        text_fields = ("id", "title", "category", "icon", "market_demand",
                       "competition_level", "future_relevance", "niche_category", "description")
        for role in self.roles:
            with self.subTest(role=role["id"]):
                for field in text_fields:
                    self.assertTrue(role.get(field), f"missing '{field}'")

                self.assertGreaterEqual(len(role["responsibilities"]), 4)
                self.assertGreaterEqual(len(role["qualifications"]), 3)
                self.assertGreaterEqual(len(role["growth_path"]), 4)
                self.assertGreaterEqual(len(role["top_companies"]), 5)

                skills = role["skills"]
                self.assertGreaterEqual(len(skills["must_have"]), 4)
                self.assertGreaterEqual(len(skills["good_to_have"]), 4)
                self.assertGreaterEqual(len(skills["can_have"]), 3)

                self.assertGreaterEqual(len(role["matching_interests"]), 3)
                self.assertGreaterEqual(len(role["matching_skills"]), 3)

    def test_salary_bands_increase_with_seniority(self):
        for role in self.roles:
            with self.subTest(role=role["id"]):
                bands = role["salary"]
                fresh, mid, senior = bands["fresher_0_1"], bands["mid_1_3"], bands["senior_3_plus"]
                for band in (fresh, mid, senior):
                    self.assertLess(band["min"], band["max"], "a salary band must have a range")
                self.assertLess(fresh["max"], mid["max"])
                self.assertLess(mid["max"], senior["max"])


class CatalogReachabilityTests(unittest.TestCase):
    """A role nobody can be matched with may as well not be in the catalog."""

    def test_every_role_is_reachable_from_at_least_one_interest_option(self):
        reachable = set()
        for option in INTEREST_OPTIONS:
            results = career_service.match_roles_smart({"interests": [option], "current_skills": []})
            reachable.update(r["role"]["id"] for r in results)

        catalog_ids = {r["id"] for r in load_catalog()}
        self.assertEqual(
            catalog_ids - reachable, set(),
            "these roles can never be matched, so no candidate would ever see them",
        )

    def test_every_role_rewards_at_least_one_known_skill(self):
        """The skill half of the score must be reachable from a real skill chip."""
        profile = {"interests": list(INTEREST_OPTIONS), "current_skills": list(SKILL_OPTIONS)}
        matches = {m["role"]["id"]: m for m in career_service.match_roles_smart(profile)}

        for role in load_catalog():
            with self.subTest(role=role["id"]):
                self.assertTrue(
                    matches[role["id"]]["matched_skills"],
                    "no SKILL_OPTIONS chip matches this role's matching_skills, so its score can never move",
                )

    def test_a_matching_score_is_between_zero_and_one_hundred(self):
        profile = {"interests": list(INTEREST_OPTIONS), "current_skills": list(SKILL_OPTIONS)}
        for match in career_service.match_roles_smart(profile):
            self.assertGreaterEqual(match["score"], 0)
            self.assertLessEqual(match["score"], 100)


class CatalogSyncTests(unittest.TestCase):
    """Startup must refresh the catalog in place — without touching user data."""

    def setUp(self):
        self._original_path = db.DB_PATH
        self._tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = os.path.join(self._tmp.name, "legacy_catalog.db")
        self.addCleanup(self._restore)

    def _restore(self):
        db.DB_PATH = self._original_path
        self._tmp.cleanup()

    def _shrink_catalog_and_add_user_work(self) -> int:
        """Simulates an older install: a one-role catalog plus a candidate's saved work."""
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("DELETE FROM roles WHERE id != ?;", (LEGACY_ROLE_ID,))
        conn.execute(
            "INSERT INTO roadmaps (user_id, role_id, role_title, roadmap_json)"
            " VALUES (0, ?, 'saved before the upgrade', '{}');",
            (LEGACY_ROLE_ID,),
        )
        conn.execute(
            "INSERT INTO tracker_topics (user_id, role_id, category, topic_name, subtopics_json, is_completed)"
            " VALUES (0, ?, 'Core', 'topic saved before the upgrade', '[]', 1);",
            (LEGACY_ROLE_ID,),
        )
        conn.commit()
        conn.close()
        return len(load_catalog())

    def _counts(self):
        conn = sqlite3.connect(db.DB_PATH)
        conn.row_factory = sqlite3.Row
        counts = {
            "roles": conn.execute("SELECT COUNT(*) FROM roles;").fetchone()[0],
            "roadmaps": conn.execute("SELECT COUNT(*) FROM roadmaps;").fetchone()[0],
            "topics": conn.execute("SELECT COUNT(*) FROM tracker_topics;").fetchone()[0],
        }
        conn.close()
        return counts

    def test_startup_adds_the_new_roles_to_an_existing_database(self):
        db.init_db()
        expected = self._shrink_catalog_and_add_user_work()

        db.init_db()

        self.assertEqual(self._counts()["roles"], expected, "every role from roles.json should be present")

    def test_startup_does_not_destroy_saved_work(self):
        db.init_db()
        self._shrink_catalog_and_add_user_work()

        db.init_db()

        counts = self._counts()
        self.assertEqual(counts["roadmaps"], 1, "a saved roadmap must survive a catalog update")
        self.assertEqual(counts["topics"], 1, "a saved tracker topic must survive a catalog update")

    def test_startup_refreshes_existing_role_content(self):
        db.init_db()
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute("UPDATE roles SET title = 'Stale Title', description = '' WHERE id = ?;", (LEGACY_ROLE_ID,))
        conn.commit()
        conn.close()

        db.init_db()

        role = career_service.get_role_by_id(LEGACY_ROLE_ID)
        from_json = next(r for r in load_catalog() if r["id"] == LEGACY_ROLE_ID)
        self.assertEqual(role["title"], from_json["title"], "an edited role should be restored from roles.json")
        self.assertEqual(role["description"], from_json["description"])

    def test_startup_never_deletes_an_unknown_role_row(self):
        """Removing a role from roles.json must not cascade away a candidate's work."""
        db.init_db()
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute(
            "INSERT INTO roles (id, title, category, icon) VALUES ('retired_role', 'Retired Role', 'Development', '💼');"
        )
        conn.commit()
        conn.close()

        db.init_db()

        self.assertIsNotNone(career_service.get_role_by_id("retired_role"))

    def test_a_broken_catalog_file_does_not_break_startup(self):
        """The catalog is read on every boot, so a bad edit must not down the API."""
        db.init_db()
        before = self._counts()["roles"]

        original_catalog = db.ROLES_JSON_PATH
        broken = os.path.join(self._tmp.name, "roles.json")
        with open(broken, "w", encoding="utf-8") as f:
            f.write('{"roles": [{"id": "oops",]')
        db.ROLES_JSON_PATH = broken
        self.addCleanup(setattr, db, "ROLES_JSON_PATH", original_catalog)

        with self.assertLogs("careercompass.db", level="WARNING"):
            db.init_db()

        self.assertEqual(self._counts()["roles"], before, "the last good catalog should stay in place")
        self.assertIsNotNone(career_service.get_role_by_id(LEGACY_ROLE_ID))


class SalaryProvenanceTests(unittest.TestCase):
    """Every band must say what it is measured against, where the figure came
    from, and when it was last reviewed.

    A salary range a candidate cannot check is just an assertion, so the
    contract is enforced on `roles.json` — the single source of truth.
    """

    MONTH = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
    KINDS = {"market", "product", "report"}

    def setUp(self):
        self.roles = load_catalog()

    def test_every_role_dates_its_salary_review(self):
        for role in self.roles:
            with self.subTest(role=role["id"]):
                self.assertRegex(role["salary"]["as_of"], self.MONTH)

    def test_every_role_cites_at_least_one_market_source(self):
        for role in self.roles:
            with self.subTest(role=role["id"]):
                sources = role["salary"]["sources"]
                self.assertTrue(sources, "a band with no source is a number with no evidence")
                self.assertTrue(
                    any(source["kind"] == "market" for source in sources),
                    "even a proxied title needs one market-wide reference point",
                )

    def test_every_source_is_attributable_and_dated(self):
        for role in self.roles:
            for source in role["salary"]["sources"]:
                with self.subTest(role=role["id"], source=source["name"]):
                    self.assertIn(source["kind"], self.KINDS)
                    self.assertTrue(source["name"])
                    self.assertTrue(source["sample"], "the reader should know how much data a figure rests on")
                    self.assertTrue(source["url"].startswith("https://"))
                    self.assertRegex(source["as_of"], self.MONTH)

    def test_a_proxied_title_explains_the_proxy(self):
        """Missing either reference point means the band was positioned by
        judgement, and that judgement has to be written down."""
        for role in self.roles:
            with self.subTest(role=role["id"]):
                salary = role["salary"]
                both_anchored = salary["market_median"] is not None and salary["product_median"] is not None
                self.assertTrue(both_anchored or salary.get("anchor_note"))

    def test_median_anchors_are_plausible(self):
        for role in self.roles:
            with self.subTest(role=role["id"]):
                for key in ("market_median", "product_median"):
                    value = role["salary"][key]
                    if value is not None:
                        self.assertGreater(value, 0)
                        self.assertLess(value, 200, "no India median for these roles is that high")

    def test_the_bands_straddle_their_reference_points(self):
        """The envelope claim: the market median and the product-company median
        must both be reachable from inside the published band."""
        for role in self.roles:
            salary = role["salary"]
            top = salary["senior_3_plus"]["max"]
            with self.subTest(role=role["id"]):
                for key in ("market_median", "product_median"):
                    value = salary[key]
                    if value is not None:
                        self.assertGreaterEqual(top, value, f"the top band should reach the {key}")


class SalaryApiTests(unittest.TestCase):
    """Provenance has to survive JSON -> SQLite -> API, not just live in the file."""

    def test_role_endpoint_returns_the_salary_provenance(self):
        response = client.get("/roles/backend_dev")
        self.assertEqual(response.status_code, 200)

        salary = response.json()["salary"]
        self.assertEqual(salary["as_of"], "2026-10")
        self.assertTrue(salary["sources"], "sources must round-trip through the database")
        self.assertIsNotNone(salary["market_median"])

    def test_every_role_from_the_api_carries_its_sources(self):
        response = client.get("/roles")
        self.assertEqual(response.status_code, 200)

        roles = response.json()
        self.assertEqual(len(roles), len(load_catalog()))
        for role in roles:
            with self.subTest(role=role["id"]):
                self.assertTrue(role["salary"]["sources"])


if __name__ == "__main__":
    unittest.main()