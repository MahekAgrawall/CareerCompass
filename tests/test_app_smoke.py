"""End-to-end smoke tests: every routed view must render without exceptions."""
import os
import sys
import unittest
import warnings

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from database.db import init_db  # noqa: E402
from services import career_service  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

init_db()
APP_PATH = os.path.join(ROOT, "app.py")
ROLE = career_service.get_role_by_id("backend_dev")

PAGES = [
    "home", "auth", "profile", "roles", "directory", "role_detail",
    "compare", "roadmap", "roadmaps", "tracker", "chat",
]


def _run_page(page, extra=None):
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["page"] = page
    # Seed state so no view makes a live AI call during tests.
    at.session_state["match_explanation"] = "Seeded for tests."
    at.session_state["selected_role"] = ROLE
    at.session_state["roadmap"] = {
        "summary": "Seeded", "immediate_focus": [], "next_level": [],
        "good_to_explore": [], "projects": [], "motivational_message": "Go",
    }
    at.session_state["compare_roles"] = [ROLE]
    at.session_state["profile"] = {
        "name": "Test", "current_skills": ["Java"],
        "interests": ["backend systems & databases"],
        "raw_interests": ["Backend Systems & Databases"],
    }
    at.session_state["user"] = {"id": 0, "name": "Test", "email": "t@t.local", "profile": None}
    for k, v in (extra or {}).items():
        at.session_state[k] = v
    at.run()
    return at


class ViewSmokeTests(unittest.TestCase):
    def test_all_pages_render(self):
        for page in PAGES:
            with self.subTest(page=page):
                at = _run_page(page)
                self.assertFalse(
                    at.exception,
                    f"{page} raised: {[e.value for e in at.exception]}",
                )

    def test_deep_link_renders(self):
        at = AppTest.from_file(APP_PATH, default_timeout=60)
        at.query_params["page"] = "role_detail"
        at.query_params["id"] = "backend_dev"
        at.run()
        self.assertFalse(at.exception, [e.value for e in at.exception])


if __name__ == "__main__":
    unittest.main()
