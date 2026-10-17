"""The prompt library — templates on disk and the AI calls that render them.

What this pins down:

* every prompt an AI call depends on exists on disk (a missing file is a
  packaging bug we want to hear about, not a silent fallback);
* placeholders are substituted, so no prompt reaches the model still containing
  a literal ``$role_title``;
* the values a caller passes actually land in the rendered prompt; and
* the copilot persona still travels as the system instruction.

No network call is made: only the model object is faked.
"""
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from tests import harness  # noqa: F401  (sys.path/cwd bootstrap first)
from services import ai_service, prompts  # noqa: E402

EXPECTED_TEMPLATES = (
    "system/roadmap.md",
    "user/roadmap.md",
    "system/match_explanation.md",
    "user/match_explanation.md",
    "system/copilot.md",
)

PROFILE = {
    "name": "Priya",
    "grad_year": "2027",
    "experience": "Fresher",
    "current_skills": ["Python", "SQL"],
    "interests": ["Machine Learning", "Cloud"],
    "location": "Pune",
}
ROLE = {
    "id": "ml-engineer",
    "title": "Machine Learning Engineer",
    "category": "Data & AI",
    "skills": {"must_have": ["Python", "PyTorch"], "good_to_have": ["MLOps"]},
}
ROADMAP = {"immediate_focus": [{"skill": "PyTorch"}, {"skill": "MLOps"}]}
VALID_ROADMAP_JSON = {
    "summary": "",
    "immediate_focus": [],
    "next_level": [],
    "good_to_explore": [],
    "projects": [],
    "motivational_message": "",
}


class PromptLibraryTests(unittest.TestCase):
    def test_every_template_the_app_uses_exists_and_is_not_empty(self):
        for name in EXPECTED_TEMPLATES:
            with self.subTest(template=name):
                self.assertTrue(prompts.load_text(name).strip(), f"{name} is empty")

    def test_missing_template_fails_loudly(self):
        with self.assertRaises(prompts.PromptNotFoundError):
            prompts.load_text("system/does-not-exist.md")

    def test_render_substitutes_every_placeholder(self):
        text = prompts.render(
            "user/roadmap.md",
            name="Priya",
            grad_year="2027",
            experience="Fresher",
            current_skills="Python, SQL",
            interests="Machine Learning",
            location="Pune",
            role_title="ML Engineer",
            role_category="Data & AI",
            must_have="Python",
            good_to_have="MLOps",
        )
        self.assertIn("Name: Priya", text)
        self.assertIn("Target Role: ML Engineer", text)
        self.assertIn("Good-to-Have Skills: MLOps", text)
        self.assertNotIn("$", text)

    def test_render_with_a_missing_value_fails(self):
        # A typo in a template or a forgotten value must not ship a raw placeholder.
        with self.assertRaises(KeyError):
            prompts.render("user/roadmap.md", name="Priya")


class AiCallPromptTests(unittest.TestCase):
    def _capture_roadmap_prompt(self) -> str:
        captured = {}

        class FakeModel:
            def generate_content(self, prompt, generation_config=None):
                captured["prompt"] = prompt
                return SimpleNamespace(text=json.dumps(VALID_ROADMAP_JSON))

        with mock.patch.object(ai_service, "get_model", return_value=FakeModel()):
            ai_service.generate_roadmap(PROFILE, ROLE)
        return captured["prompt"]

    def test_roadmap_call_injects_the_candidate_and_role(self):
        prompt = self._capture_roadmap_prompt()
        for expected in ("Priya", "2027", "Machine Learning Engineer", "PyTorch", "MLOps", "Pune"):
            self.assertIn(expected, prompt)
        self.assertNotIn("$", prompt)

    def test_roadmap_call_keeps_the_json_schema(self):
        prompt = self._capture_roadmap_prompt()
        self.assertIn('"immediate_focus"', prompt)
        self.assertIn("strictly as a JSON object", prompt)

    def test_match_explanation_injects_skills_interests_and_titles(self):
        captured = {}

        class FakeModel:
            def generate_content(self, prompt):
                captured["prompt"] = prompt
                return SimpleNamespace(text="ok")

        with mock.patch.object(ai_service, "get_model", return_value=FakeModel()):
            ai_service.generate_role_match_explanation(PROFILE, [ROLE])

        self.assertIn("Python, SQL", captured["prompt"])
        self.assertIn("Machine Learning, Cloud", captured["prompt"])
        self.assertIn("Machine Learning Engineer", captured["prompt"])
        self.assertNotIn("$", captured["prompt"])

    def test_copilot_persona_travels_as_the_system_instruction(self):
        captured = {}

        class FakeChat:
            def start_chat(self, history=None):
                return self

            def send_message(self, message, stream=False):
                return SimpleNamespace(text="ok")

        def fake_get_model(system_instruction=None):
            captured["system"] = system_instruction
            return FakeChat()

        with mock.patch.object(ai_service, "get_model", side_effect=fake_get_model):
            ai_service.send_chat_message(PROFILE, ROLE, ROADMAP, "hi", [])

        self.assertIn("CareerCompass Copilot", captured["system"])
        self.assertIn("Machine Learning Engineer", captured["system"])
        self.assertIn("PyTorch, MLOps", captured["system"])
        self.assertNotIn("$", captured["system"])


if __name__ == "__main__":
    unittest.main()
