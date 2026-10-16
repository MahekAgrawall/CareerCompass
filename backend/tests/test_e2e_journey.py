"""End-to-end journey tests: a candidate's whole path through the API.

These walk the happy path a real candidate takes — browse the catalog, register,
sign in, answer the questionnaire, read ranked matches, open a role, plan a
study schedule, tick off syllabus topics and reach the saved library — asserting
the contract at every hop, including that progress survives a new session.

Isolation (throwaway database) comes from `tests.harness`.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.harness import client, unique_email  # noqa: E402

from services import ai_service, auth_service  # noqa: E402

PASSWORD = "password123"
ROLE_ID = "backend_dev"
TARGET_LANGUAGES = ["Java", "PostgreSQL (Relational)", "Spring Boot 3 (Java)"]
ANSWERS = {
    "name": "Journey Candidate",
    "grad_year": "2026",
    "experience": "Student / Fresher",
    "location": "Bangalore",
    "current_skills": ["Java", "SQL / MySQL / PostgreSQL"],
    "interests": ["backend systems & databases"],
}


def _login(email: str) -> dict:
    """Signs in and returns an Authorization header (a fresh 'session')."""
    r = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class EndToEndJourneyTests(unittest.TestCase):
    def test_first_visit_to_saved_progress(self):
        # 1. Landing page — the role catalog is public.
        catalog = client.get("/roles")
        self.assertEqual(catalog.status_code, 200)
        catalog_ids = {role["id"] for role in catalog.json()}
        self.assertIn(ROLE_ID, catalog_ids)

        categories = client.get("/roles/categories")
        self.assertEqual(categories.status_code, 200)
        self.assertTrue(categories.json())

        # 2. Register.
        email = unique_email()
        registered = client.post("/auth/signup", json={
            "name": "Journey Candidate", "email": email, "password": PASSWORD,
        })
        self.assertEqual(registered.status_code, 201, registered.text)
        self.assertEqual(registered.json()["user"]["email"], email)

        # 3. Sign in and confirm the session identity.
        auth = _login(email)
        me = client.get("/auth/me", headers=auth)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], email)

        # A brand-new candidate owns no profile and nothing saved.
        self.assertEqual(client.get("/profile", headers=auth).json(), {})
        self.assertEqual(client.get("/roadmaps", headers=auth).json(), [])

        # 4. Answer the profile questionnaire.
        saved = client.put("/profile", json=ANSWERS, headers=auth)
        self.assertEqual(saved.status_code, 200, saved.text)

        profile = client.get("/profile", headers=auth).json()
        self.assertEqual(profile["name"], ANSWERS["name"])
        self.assertEqual(profile["current_skills"], ANSWERS["current_skills"])
        self.assertEqual(profile["interests"], ANSWERS["interests"])

        # 5. Read ranked matches (deterministic; explain=False keeps it fast).
        matched = client.post("/match", json={
            "interests": ANSWERS["interests"],
            "current_skills": ANSWERS["current_skills"],
            "explain": False,
        }, headers=auth)
        self.assertEqual(matched.status_code, 200, matched.text)
        results = matched.json()["results"]
        self.assertTrue(results)

        scores = [item["score"] for item in results]
        self.assertEqual(scores, sorted(scores, reverse=True), "matches must be ranked")
        for item in results:
            self.assertIn(item["role"]["id"], catalog_ids, "matches must be real roles")
            self.assertTrue(item["matched_interests"], "no match without interest synergy")
            self.assertTrue(0 <= item["score"] <= 100)

        # 6. Open a role detail page.
        chosen = ROLE_ID
        detail = client.get(f"/roles/{chosen}", headers=auth)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["id"], chosen)
        self.assertTrue(detail.json()["title"])
        self.assertIn("salary", detail.json())

        # The study-stack catalogue is public — static config, not user data.
        stack = client.get(f"/tracker/stack/{chosen}")
        self.assertEqual(stack.status_code, 200)
        self.assertIn("dim1", stack.json())

        # 7. Plan study time and get a syllabus.
        planning = client.put("/tracker/schedule", json={
            "role_id": chosen, "weekday_hours": 2.0, "weekend_hours": 4.0,
            "target_languages": TARGET_LANGUAGES,
        }, headers=auth)
        self.assertEqual(planning.status_code, 200, planning.text)
        planned = planning.json()
        self.assertEqual(planned["schedule"]["weekly_total_hours"], 18.0)
        self.assertTrue(planned["topics"])
        self.assertIn("metrics", planned)

        # 8. Tick off a syllabus topic; the change must persist.
        topics = client.get(f"/tracker/topics/{chosen}", headers=auth).json()["topics"]
        self.assertTrue(topics)
        topic_id = topics[0]["id"]
        self.assertFalse(topics[0]["is_completed"])

        ticked = client.patch(
            f"/tracker/topics/{topic_id}", json={"is_completed": True}, headers=auth
        )
        self.assertEqual(ticked.status_code, 200, ticked.text)
        self.assertTrue(ticked.json()["is_completed"])

        refreshed = client.get(f"/tracker/topics/{chosen}", headers=auth).json()["topics"]
        self.assertTrue(next(t for t in refreshed if t["id"] == topic_id)["is_completed"])

        # 9. Generate a roadmap. Live generation needs network access and a slow,
        #    non-deterministic model, so it is exercised manually rather than here;
        #    without a key the API must degrade gracefully instead of erroring.
        if not ai_service.is_configured():
            blocked = client.post("/roadmap", json={"role_id": chosen, "profile": ANSWERS}, headers=auth)
            self.assertEqual(blocked.status_code, 503, blocked.text)
            self.assertTrue(blocked.json()["detail"])

        # 10. Saved library round-trip. Generation is what persists a roadmap, but
        #     it is unavailable here, so seed one through the same service call.
        role_title = detail.json()["title"]
        auth_service.save_roadmap(me.json()["id"], chosen, role_title, {"summary": "seeded"})

        library = client.get("/roadmaps", headers=auth)
        self.assertEqual(library.status_code, 200)
        saved_roadmaps = library.json()
        self.assertEqual(len(saved_roadmaps), 1)
        self.assertEqual(saved_roadmaps[0]["role_id"], chosen)
        self.assertEqual(saved_roadmaps[0]["role_title"], role_title)

        removed = client.delete(f"/roadmaps/{saved_roadmaps[0]['id']}", headers=auth)
        self.assertEqual(removed.status_code, 204)
        self.assertEqual(client.get("/roadmaps", headers=auth).json(), [])

    def test_progress_survives_a_new_session(self):
        """Close the browser and come back: the work is still there."""
        email = unique_email()
        registered = client.post("/auth/signup", json={
            "name": "Returning Candidate", "email": email, "password": PASSWORD,
        })
        self.assertEqual(registered.status_code, 201, registered.text)

        # First session: plan study time and complete a topic.
        first = _login(email)
        planned = client.put("/tracker/schedule", json={
            "role_id": ROLE_ID, "weekday_hours": 2.0, "weekend_hours": 4.0,
            "target_languages": TARGET_LANGUAGES,
        }, headers=first)
        self.assertEqual(planned.status_code, 200, planned.text)

        topics = client.get(f"/tracker/topics/{ROLE_ID}", headers=first).json()["topics"]
        self.assertTrue(topics)
        topic_id = topics[0]["id"]
        self.assertEqual(client.patch(
            f"/tracker/topics/{topic_id}", json={"is_completed": True}, headers=first
        ).status_code, 200)

        # Second session: a brand-new token, as after a browser restart.
        second = _login(email)
        schedule = client.get(f"/tracker/schedule/{ROLE_ID}", headers=second).json()
        self.assertEqual(schedule["weekday_hours"], 2.0)
        self.assertEqual(schedule["weekly_total_hours"], 18.0)

        resumed = client.get(f"/tracker/topics/{ROLE_ID}", headers=second).json()["topics"]
        self.assertTrue(next(t for t in resumed if t["id"] == topic_id)["is_completed"])


if __name__ == "__main__":
    unittest.main()
