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

# app.config requires a real JWT_SECRET (no insecure fallback). Supply a
# test-only value unless the environment already provides one (e.g. in CI).
os.environ.setdefault("JWT_SECRET", "test-only-secret-" + "0" * 40)

from app.main import app  # noqa: E402
from services import ai_service, auth_service  # noqa: E402

client = TestClient(app)


def setUpModule():
    db.init_db()


def tearDownModule():
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


def _unique_email() -> str:
    return f"test_{uuid.uuid4().hex[:10]}@example.com"


def _signup(name: str = "Test User") -> dict:
    """Creates a fresh account and returns an Authorization header for it."""
    email = _unique_email()
    r = client.post("/auth/signup", json={"name": name, "email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


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
        headers = _signup("Tracker User")

        # The stack catalogue is public — it is static config, not user data.
        r = client.get("/tracker/stack/backend_dev")
        self.assertEqual(r.status_code, 200)
        self.assertIn("dim1", r.json())

        r = client.get("/tracker/topics/backend_dev", headers=headers)
        self.assertEqual(r.status_code, 200)
        topics = r.json()["topics"]
        self.assertTrue(topics)

        topic_id = topics[0]["id"]
        toggle = client.patch(f"/tracker/topics/{topic_id}", json={"is_completed": True}, headers=headers)
        self.assertEqual(toggle.status_code, 200)
        self.assertTrue(toggle.json()["is_completed"])

    def test_save_schedule(self):
        headers = _signup("Scheduler")
        r = client.put("/tracker/schedule", json={
            "role_id": "backend_dev",
            "weekday_hours": 2.0,
            "weekend_hours": 4.0,
            "target_languages": ["Java", "PostgreSQL (Relational)", "Spring Boot 3 (Java)"],
        }, headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["schedule"]["weekly_total_hours"], 18.0)
        self.assertTrue(body["topics"])


class TrackerAccessControlTests(unittest.TestCase):
    """Progress records must be private to their owner."""

    def test_tracker_state_requires_authentication(self):
        self.assertEqual(client.get("/tracker/schedule/backend_dev").status_code, 401)
        self.assertEqual(client.get("/tracker/topics/backend_dev").status_code, 401)
        self.assertEqual(
            client.patch("/tracker/topics/1", json={"is_completed": True}).status_code, 401
        )
        self.assertEqual(
            client.put("/tracker/schedule", json={
                "role_id": "backend_dev", "weekday_hours": 2.0,
                "weekend_hours": 4.0, "target_languages": [],
            }).status_code,
            401,
        )

    def test_user_cannot_toggle_another_users_topic(self):
        alice = _signup("Alice")
        bob = _signup("Bob")

        topics = client.get("/tracker/topics/backend_dev", headers=alice).json()["topics"]
        self.assertTrue(topics)
        topic_id = topics[0]["id"]
        self.assertFalse(topics[0]["is_completed"])

        # Bob cannot modify Alice's topic...
        denied = client.patch(f"/tracker/topics/{topic_id}", json={"is_completed": True}, headers=bob)
        self.assertEqual(denied.status_code, 404)

        # ...and Alice's record stays untouched.
        after = client.get("/tracker/topics/backend_dev", headers=alice).json()["topics"]
        self.assertFalse(next(t for t in after if t["id"] == topic_id)["is_completed"])

        # Alice can still update her own topic.
        ok = client.patch(f"/tracker/topics/{topic_id}", json={"is_completed": True}, headers=alice)
        self.assertEqual(ok.status_code, 200)

    def test_unknown_topic_id_returns_404(self):
        headers = _signup("Nora")
        r = client.patch("/tracker/topics/999999", json={"is_completed": True}, headers=headers)
        self.assertEqual(r.status_code, 404)

    def test_schedules_are_isolated_per_user(self):
        alice = _signup("Alice S")
        bob = _signup("Bob S")

        client.put("/tracker/schedule", json={
            "role_id": "backend_dev", "weekday_hours": 3.0,
            "weekend_hours": 5.0, "target_languages": [],
        }, headers=alice)

        self.assertEqual(
            client.get("/tracker/schedule/backend_dev", headers=alice).json()["weekday_hours"], 3.0
        )
        # Bob gets the defaults, never Alice's values.
        self.assertEqual(
            client.get("/tracker/schedule/backend_dev", headers=bob).json()["weekday_hours"], 1.5
        )


class ProfileAccessControlTests(unittest.TestCase):
    def test_profile_requires_authentication(self):
        self.assertEqual(client.get("/profile").status_code, 401)
        self.assertEqual(client.put("/profile", json={}).status_code, 401)

    def test_profiles_are_private(self):
        alice = _signup("P Alice")
        bob = _signup("P Bob")

        client.put("/profile", json={
            "name": "Alice", "grad_year": "2025", "experience": "Student / Fresher",
            "location": "Bangalore", "current_skills": ["Java"],
            "interests": ["Coding & Problem Solving"],
        }, headers=alice)

        self.assertEqual(client.get("/profile", headers=alice).json()["name"], "Alice")
        self.assertNotEqual(client.get("/profile", headers=bob).json().get("name"), "Alice")


class RoadmapAccessControlTests(unittest.TestCase):
    def test_roadmaps_require_authentication(self):
        self.assertEqual(client.get("/roadmaps").status_code, 401)
        self.assertEqual(client.delete("/roadmaps/1").status_code, 401)

    def test_saved_roadmaps_are_scoped_to_the_owner(self):
        alice = _signup("R Alice")
        bob = _signup("R Bob")

        alice_id = client.get("/auth/me", headers=alice).json()["id"]
        auth_service.save_roadmap(
            alice_id, "backend_dev", "Backend Developer",
            {"summary": "seed", "immediate_focus": [], "next_level": [],
             "good_to_explore": [], "projects": []},
        )

        alice_list = client.get("/roadmaps", headers=alice).json()
        self.assertTrue(alice_list)
        self.assertEqual(client.get("/roadmaps", headers=bob).json(), [])

        roadmap_id = alice_list[0]["id"]
        # Bob's delete is a no-op on Alice's record...
        self.assertEqual(client.delete(f"/roadmaps/{roadmap_id}", headers=bob).status_code, 204)
        self.assertTrue(client.get("/roadmaps", headers=alice).json())
        # ...while Alice can delete her own.
        self.assertEqual(client.delete(f"/roadmaps/{roadmap_id}", headers=alice).status_code, 204)
        self.assertEqual(client.get("/roadmaps", headers=alice).json(), [])


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
