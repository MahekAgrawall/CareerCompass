"""Schema-migration tests for the profiles table.

The questionnaire gained questions after the first databases were created, and
SQLite's `CREATE TABLE IF NOT EXISTS` leaves already-created tables alone — so
`init_db()` has to append the new columns in place. These tests start from the
old shape and assert the upgrade keeps every existing row.
"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.harness import client  # noqa: E402,F401  (points the live DB at a throwaway file)

from database import db  # noqa: E402
from services import application_service, auth_service  # noqa: E402

NEW_COLUMNS = ("work_mode", "open_to_relocate", "career_goal")

# The profiles table exactly as it shipped before the questionnaire grew.
OLD_PROFILES_TABLE = """
    CREATE TABLE profiles (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        grad_year TEXT,
        experience TEXT,
        location TEXT,
        current_skills_json TEXT,
        interests_json TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
"""


class ProfileMigrationTests(unittest.TestCase):
    def setUp(self):
        self._original_path = db.DB_PATH
        self._tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = os.path.join(self._tmp.name, "legacy.db")
        self.addCleanup(self._restore)

    def _restore(self):
        db.DB_PATH = self._original_path
        self._tmp.cleanup()

    def _legacy_database(self):
        """Writes a pre-questionnaire database holding one answered profile."""
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute(OLD_PROFILES_TABLE)
        conn.execute(
            "INSERT INTO profiles (user_id, name, grad_year, experience, location,"
            " current_skills_json, interests_json) VALUES (?, ?, ?, ?, ?, ?, ?);",
            (7, "Legacy Candidate", "2025", "Student / Fresher", "Pune",
             '["Java"]', '["backend systems & databases"]'),
        )
        conn.commit()
        conn.close()

    def test_init_db_upgrades_an_existing_database_in_place(self):
        self._legacy_database()

        db.init_db()

        conn = sqlite3.connect(db.DB_PATH)
        conn.row_factory = sqlite3.Row
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(profiles);")}
        self.assertTrue(set(NEW_COLUMNS) <= columns, f"missing columns: {set(NEW_COLUMNS) - columns}")

        row = conn.execute("SELECT * FROM profiles WHERE user_id = 7;").fetchone()
        conn.close()
        self.assertIsNotNone(row, "the upgrade must not drop existing profiles")
        self.assertEqual(row["name"], "Legacy Candidate")
        self.assertEqual(row["grad_year"], "2025")
        for column in NEW_COLUMNS:
            self.assertIsNone(row[column], "a migrated row has no answer for the new questions")

    def test_init_db_is_idempotent(self):
        """Starting up twice must not fail or duplicate columns."""
        self._legacy_database()
        db.init_db()
        db.init_db()

        conn = sqlite3.connect(db.DB_PATH)
        names = [row[1] for row in conn.execute("PRAGMA table_info(profiles);")]
        conn.close()
        for column in NEW_COLUMNS:
            self.assertEqual(names.count(column), 1, f"{column} added more than once")

    def test_migrated_profile_reads_back_with_empty_answers(self):
        """A legacy row surfaces as empty strings, not nulls, over the API contract."""
        self._legacy_database()
        db.init_db()

        profile = auth_service.get_user_profile(7)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["name"], "Legacy Candidate")
        self.assertEqual(profile["interests"], ["backend systems & databases"])
        for field in NEW_COLUMNS:
            self.assertEqual(profile[field], "", f"{field} should be an empty string")


class RoadmapProvenanceMigrationTests(unittest.TestCase):
    """Saved plans gained a recipe (model + prompt wording) after the first ones existed."""

    def setUp(self):
        self._original_path = db.DB_PATH
        self._tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = os.path.join(self._tmp.name, "legacy_roadmaps.db")
        self.addCleanup(self._restore)

    def _restore(self):
        db.DB_PATH = self._original_path
        self._tmp.cleanup()

    def test_an_existing_plan_survives_and_reports_empty_provenance(self):
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute("""
            CREATE TABLE roadmaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                role_id TEXT NOT NULL,
                role_title TEXT NOT NULL,
                roadmap_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute(
            "INSERT INTO roadmaps (user_id, role_id, role_title, roadmap_json) VALUES (?, ?, ?, ?);",
            (7, "backend_dev", "Backend Developer", '{"summary": "legacy"}'),
        )
        conn.commit()
        conn.close()

        db.init_db()

        conn = sqlite3.connect(db.DB_PATH)
        conn.row_factory = sqlite3.Row
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(roadmaps);")}
        self.assertTrue({"model", "prompt_version"} <= columns, f"missing: {columns}")
        row = conn.execute("SELECT * FROM roadmaps WHERE user_id = 7;").fetchone()
        conn.close()

        self.assertIsNotNone(row, "the upgrade must not drop existing plans")
        self.assertEqual(row["role_title"], "Backend Developer")
        self.assertIsNone(row["model"], "a plan written before provenance has no recipe")

        saved = auth_service.get_saved_roadmaps(7)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["roadmap"], {"summary": "legacy"})
        self.assertEqual(saved[0]["model"], "", "an unknown recipe reads back as empty, not null")
        self.assertEqual(saved[0]["prompt_version"], "")


class SavedJobsMigrationTests(unittest.TestCase):
    """Application tracking arrived after the first databases were in use."""

    def setUp(self):
        self._original_path = db.DB_PATH
        self._tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = os.path.join(self._tmp.name, "legacy_saved_jobs.db")
        self.addCleanup(self._restore)

    def _restore(self):
        db.DB_PATH = self._original_path
        self._tmp.cleanup()

    def _legacy_database(self):
        """A database from before saved jobs existed: an account and nothing else."""
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute(
            "INSERT INTO users (id, name, email, password_hash)"
            " VALUES (7, 'Legacy Candidate', 'legacy@example.com', 'x');"
        )
        conn.commit()
        conn.close()

    def test_init_db_adds_the_table_to_an_existing_database(self):
        self._legacy_database()

        db.init_db()

        conn = sqlite3.connect(db.DB_PATH)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}
        conn.close()
        self.assertIn("saved_jobs", tables, "an existing database gains the table in place")

    def test_a_filed_application_survives_a_restart(self):
        """The point of the table: the row outlives the process that wrote it."""
        self._legacy_database()
        db.init_db()

        application_service.save_application(7, {
            "posting_id": "himalayas:data-analyst",
            "title": "Data Analyst",
            "company": "Bright Metrics",
            "location": "Remote",
            "remote": True,
        })

        db.init_db()  # a restart

        saved = application_service.list_applications(7)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["title"], "Data Analyst")
        self.assertTrue(saved[0]["remote"])
        self.assertEqual(saved[0]["status"], "saved")


if __name__ == "__main__":
    unittest.main()
