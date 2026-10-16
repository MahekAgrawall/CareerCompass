"""Service-layer unit tests for CareerCompass (stdlib unittest, no extra deps)."""
import hashlib
import os
import sys
import unittest
import warnings

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from database.db import init_db  # noqa: E402
from services import auth_service, career_service, tracker_service, ai_service  # noqa: E402
from ui.views import roadmap_view  # noqa: E402


def setUpModule():
    init_db()


class PasswordHashingTests(unittest.TestCase):
    def test_pbkdf2_roundtrip(self):
        h = auth_service._hash_password("supersecret")
        self.assertTrue(h.startswith("pbkdf2_sha256$"))
        self.assertTrue(auth_service._verify_password("supersecret", h))
        self.assertFalse(auth_service._verify_password("nope", h))

    def test_salt_is_random(self):
        self.assertNotEqual(
            auth_service._hash_password("same"),
            auth_service._hash_password("same"),
        )

    def test_legacy_sha256_still_verifies(self):
        legacy = hashlib.sha256(b"oldpass").hexdigest()
        self.assertTrue(auth_service._verify_password("oldpass", legacy))
        self.assertFalse(auth_service._verify_password("bad", legacy))

    def test_no_global_session_functions(self):
        for name in ("remember_session", "get_remembered_session", "clear_saved_session"):
            self.assertFalse(hasattr(auth_service, name))


class MatchingTests(unittest.TestCase):
    def test_every_result_has_interest_alignment(self):
        profile = {"interests": ["backend systems & databases"],
                   "current_skills": ["Java", "SQL / MySQL / PostgreSQL"]}
        results = career_service.match_roles_smart(profile)
        self.assertTrue(results)
        for r in results:
            self.assertTrue(r["matched_interests"])
            self.assertGreaterEqual(r["score"], 0)
            self.assertLessEqual(r["score"], 100)

    def test_sorted_descending(self):
        profile = {"interests": ["cloud, devops & linux"], "current_skills": ["Docker", "Linux"]}
        scores = [r["score"] for r in career_service.match_roles_smart(profile)]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_no_interests_returns_empty(self):
        self.assertEqual(
            career_service.match_roles_smart({"interests": [], "current_skills": ["Java"]}),
            [],
        )


class TrackerTests(unittest.TestCase):
    def test_every_role_has_a_stack(self):
        for role in career_service.get_all_roles():
            schema = tracker_service.get_role_stack_schema(role["id"])
            self.assertIn("dim1", schema)
            self.assertTrue(schema["dim1"]["options"])

    def test_ml_topics_include_deep_learning_and_mlops(self):
        topics = tracker_service.build_topics_from_choices(
            "ml_engineer",
            ["Python (PyTorch)", "Hugging Face Transformers", "MLflow Tracking & Model Registry"],
        )
        categories = {t["category"] for t in topics}
        self.assertIn("Deep Learning", categories)
        self.assertIn("MLOps & Production ML", categories)

    def test_metrics_math(self):
        topics = [
            {"is_completed": True, "estimated_hours": 5.0},
            {"is_completed": False, "estimated_hours": 5.0},
        ]
        m = tracker_service.calculate_tracker_metrics(topics, weekly_hours=5.0)
        self.assertEqual(m["percentage"], 50)
        self.assertEqual(m["remaining_hours"], 5.0)
        self.assertEqual(m["weeks_remaining"], 1.0)


class AIServiceTests(unittest.TestCase):
    def test_extract_json_from_fenced_block(self):
        self.assertEqual(ai_service._extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_extract_json_from_prose(self):
        self.assertEqual(ai_service._extract_json('here you go: {"a": 2} thanks'), {"a": 2})

    def test_validate_roadmap_rejects_missing_fields(self):
        with self.assertRaises(ValueError):
            ai_service._validate_roadmap({"summary": "x"})

    def test_validate_roadmap_accepts_complete(self):
        ai_service._validate_roadmap({
            "summary": "x", "immediate_focus": [], "next_level": [],
            "good_to_explore": [], "projects": [],
        })

    def test_stream_chat_is_generator(self):
        import inspect
        self.assertTrue(inspect.isgeneratorfunction(ai_service.stream_chat_message))


class RoadmapExportTests(unittest.TestCase):
    def test_markdown_contains_phases_and_skills(self):
        role = career_service.get_role_by_id("backend_dev")
        roadmap = {
            "summary": "s",
            "immediate_focus": [{"skill": "DSA", "why": "w", "resource": "r", "time_estimate": "2w"}],
            "next_level": [], "good_to_explore": [], "projects": [],
            "motivational_message": "go",
        }
        md = roadmap_view._roadmap_to_markdown({"name": "T"}, role, roadmap)
        for token in ["# ", "Phase 1", "DSA", "go"]:
            self.assertIn(token, md)


if __name__ == "__main__":
    unittest.main()
