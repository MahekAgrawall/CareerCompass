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
from services import auth_service  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
