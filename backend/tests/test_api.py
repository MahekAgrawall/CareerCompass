"""API integration tests (FastAPI TestClient).

Every test runs against a throwaway SQLite database provided by `tests.harness`,
so none of them can read or mutate a developer's real `backend/data/career_compass.db`.
"""
import os
import sys
import unittest
from unittest import mock

# Supports both package discovery and `python tests/test_api.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.harness import client, signup, unique_email  # noqa: E402

from services import ai_service, auth_service, career_service  # noqa: E402


class AuthFlowTests(unittest.TestCase):
    def test_signup_login_me(self):
        email = unique_email()
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
        email = unique_email()
        payload = {"name": "Dup", "email": email, "password": "password123"}
        self.assertEqual(client.post("/auth/signup", json=payload).status_code, 201)
        self.assertEqual(client.post("/auth/signup", json=payload).status_code, 400)

    def test_login_wrong_password(self):
        email = unique_email()
        client.post("/auth/signup", json={"name": "X", "email": email, "password": "password123"})
        r = client.post("/auth/login", json={"email": email, "password": "wrongpass"})
        self.assertEqual(r.status_code, 401)

    def test_me_requires_token(self):
        self.assertEqual(client.get("/auth/me").status_code, 401)

    def test_short_password_rejected(self):
        r = client.post("/auth/signup", json={"name": "X", "email": unique_email(), "password": "short"})
        self.assertEqual(r.status_code, 422)


class RolesTests(unittest.TestCase):
    def test_list_roles(self):
        r = client.get("/roles")
        self.assertEqual(r.status_code, 200)
        # The exact catalog size lives in roles.json; this only guards the endpoint contract.
        self.assertGreaterEqual(len(r.json()), 25)

    def test_categories_are_the_declared_vocabulary(self):
        """The Directory's dropdown renders this list, so the endpoint's contract
        is the *vocabulary*: the eight categories the catalog is organised into,
        then the escape hatch for a role the taxonomy cannot place."""
        r = client.get("/roles/categories")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [*career_service.ROLE_CATEGORIES, career_service.OTHER_CATEGORY])
        self.assertNotIn(
            career_service.ALL_CATEGORIES, r.json(),
            "All Categories is the dropdown's default, not a category any role carries",
        )

    def test_every_served_role_has_a_category_the_dropdown_offers(self):
        """The filter has to be total: a label the dropdown cannot offer would
        make that role invisible to anyone filtering by category."""
        categories = client.get("/roles/categories").json()
        roles = client.get("/roles").json()
        self.assertTrue(roles)
        for role in roles:
            with self.subTest(role=role["id"]):
                self.assertIn(role["category"], categories)

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
        headers = signup("Tracker User")

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
        headers = signup("Scheduler")
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
        alice = signup("Alice")
        bob = signup("Bob")

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
        headers = signup("Nora")
        r = client.patch("/tracker/topics/999999", json={"is_completed": True}, headers=headers)
        self.assertEqual(r.status_code, 404)

    def test_schedules_are_isolated_per_user(self):
        alice = signup("Alice S")
        bob = signup("Bob S")

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
        alice = signup("P Alice")
        bob = signup("P Bob")

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
        alice = signup("R Alice")
        bob = signup("R Bob")

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


class RoadmapProvenanceTests(unittest.TestCase):
    """A saved plan records what produced it, not just when it was produced."""

    def test_generating_records_the_model_and_the_prompt_wording(self):
        headers = signup("Provenance")
        roadmap = {
            "summary": "", "immediate_focus": [], "next_level": [],
            "good_to_explore": [], "projects": [],
        }

        # The generation itself needs a live model; the persistence path does not.
        with mock.patch.object(ai_service, "generate_roadmap", return_value=roadmap):
            generated = client.post(
                "/roadmap",
                json={"role_id": "backend_dev", "profile": {"name": "Provenance"}},
                headers=headers,
            )
        self.assertEqual(generated.status_code, 200, generated.text)

        saved = client.get("/roadmaps", headers=headers).json()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["role_id"], "backend_dev")
        self.assertEqual(saved[0]["model"], ai_service.MODEL_NAME)
        self.assertEqual(saved[0]["prompt_version"], ai_service.roadmap_prompt_version())


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
