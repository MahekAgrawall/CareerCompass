"""API integration tests (FastAPI TestClient).

These tests run against a throwaway SQLite database inside a temporary directory,
so they can never read or mutate a developer's real `backend/data/career_compass.db`.
"""
import os
import shutil
import sys
import tempfile
import unittest
import uuid
import warnings

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from fastapi.testclient import TestClient  # noqa: E402

import database.db as db  # noqa: E402

# Redirect persistence to an isolated temp DB *before* the app or init_db is used.
_TMP_DIR = tempfile.mkdtemp(prefix="careercompass_tests_")
db.DB_PATH = os.path.join(_TMP_DIR, "career_compass_test.db")

from app.main import app  # noqa: E402
from services import ai_service  # noqa: E402

client = TestClient(app)


def setUpModule():
    db.init_db()


def tearDownModule():
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


def _unique_email() -> str:
    return f"test_{uuid.uuid4().hex[:10]}@example.com"


class AuthFlowTests(unittest.TestCase):
    def test_signup_login_me(self):
        email = _unique_email()
        r = client.post("/auth/signup", json={"name": "Test User", "email": email, "password": "password123"})
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertIn("access_token", body)
        self.assertEqual(body["user"]["email"], email)

        token = body["access_token"]
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], email)

        login = client.post("/auth/login", json={"email": email, "password": "password123"})
        self.assertEqual(login.status_code, 200)

    def test_duplicate_signup_rejected(self):
        email = _unique_email()
        payload = {"name": "Dup", "email": email, "password": "password123"}
        self.assertEqual(client.post("/auth/signup", json=payload).status_code, 201)
        self.assertEqual(client.post("/auth/signup", json=payload).status_code, 400)

    def test_login_wrong_password(self):
        email = _unique_email()
        client.post("/auth/signup", json={"name": "X", "email": email, "password": "password123"})
        r = client.post("/auth/login", json={"email": email, "password": "wrongpass"})
        self.assertEqual(r.status_code, 401)

    def test_me_requires_token(self):
        self.assertEqual(client.get("/auth/me").status_code, 401)

    def test_short_password_rejected(self):
        r = client.post("/auth/signup", json={"name": "X", "email": _unique_email(), "password": "short"})
        self.assertEqual(r.status_code, 422)


class RolesTests(unittest.TestCase):
    def test_list_roles(self):
        r = client.get("/roles")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 15)

    def test_categories(self):
        r = client.get("/roles/categories")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json())

    def test_get_role(self):
        r = client.get("/roles/backend_dev")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], "backend_dev")

    def test_missing_role_404(self):
        self.assertEqual(client.get("/roles/does_not_exist").status_code, 404)


class MatchTests(unittest.TestCase):
    def test_match_without_ai(self):
        r = client.post("/match", json={
            "interests": ["backend systems & databases"],
            "current_skills": ["Java", "SQL / MySQL / PostgreSQL"],
            "explain": False,
        })
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["results"])
        for item in body["results"]:
            self.assertTrue(item["matched_interests"])
            self.assertIn("role", item)


class TrackerTests(unittest.TestCase):
    def test_stack_and_topics_and_toggle(self):
        r = client.get("/tracker/stack/backend_dev")
        self.assertEqual(r.status_code, 200)
        self.assertIn("dim1", r.json())

        r = client.get("/tracker/topics/backend_dev")
        self.assertEqual(r.status_code, 200)
        topics = r.json()["topics"]
        self.assertTrue(topics)

        topic_id = topics[0]["id"]
        toggle = client.patch(f"/tracker/topics/{topic_id}", json={"is_completed": True})
        self.assertEqual(toggle.status_code, 200)
        self.assertTrue(toggle.json()["is_completed"])

    def test_save_schedule(self):
        r = client.put("/tracker/schedule", json={
            "role_id": "backend_dev",
            "weekday_hours": 2.0,
            "weekend_hours": 4.0,
            "target_languages": ["Java", "PostgreSQL (Relational)", "Spring Boot 3 (Java)"],
        })
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["schedule"]["weekly_total_hours"], 18.0)
        self.assertTrue(body["topics"])


class MetaTests(unittest.TestCase):
    def test_health(self):
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_roadmap_reports_missing_key(self):
        if ai_service.is_configured():
            self.skipTest("Gemini key present; skipping offline-only assertion")
        r = client.post("/roadmap", json={"role_id": "backend_dev", "profile": {"name": "T"}})
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
