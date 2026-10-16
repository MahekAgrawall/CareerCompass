"""Study-plan tests: every catalogued role gets a tailored, non-empty syllabus.

`data/stacks.json` supplies the per-role, three-dimension stack selector and
`build_topics_from_choices()` turns the picked options into study topics. When
the catalogue grew from its original 15 roles to 30, both halves needed content
for the newer specialisations (mobile, games, embedded, design, offensive
security, ...), so this module guards that:

1. **coverage** — every role in `roles.json` has a tailored stack, and every
   option in every stack maps onto at least one topic;
2. **plan shape** — every combination of options produces a non-empty,
   duplicate-free plan with real content and hours;
3. **no regressions** — the newer syllabus blocks are keyed on keywords that
   never appear in the original roles' stacks, and those roles' shipped plans
   are pinned below.
"""
import itertools
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.harness import client, signup  # noqa: E402,F401  (points the live DB at a throwaway file)

from database import db  # noqa: E402
from services import tracker_service  # noqa: E402

DSA_TOPIC = "Data Structures & Algorithmic Problem Solving"

# The roles that shipped before the catalogue was expanded. Their study plans are
# a shipped contract: a candidate may already have ticks recorded against them.
ORIGINAL_ROLE_IDS = (
    "ai_agent_engineer",
    "backend_dev",
    "business_analyst",
    "cloud_engineer",
    "cybersecurity_analyst",
    "data_analyst",
    "data_engineer",
    "data_scientist",
    "forward_deployed_engineer",
    "frontend_dev",
    "fullstack_dev",
    "ml_engineer",
    "product_manager",
    "qa_automation_engineer",
    "sre_platform_engineer",
)

# The plan a brand-new candidate gets for a role: the first option in each dimension.
SHIPPED_PLANS = {
    "backend_dev": [
        "Java Fundamentals, OOP Architecture & Memory Model",
        "Collections Framework & Modern Streams API",
        "Multithreading, Concurrency & Virtual Threads",
        "Relational Data Modeling & Advanced SQL Optimization",
        "Spring Boot 3, JPA/Hibernate & Security",
        "Data Structures & Algorithmic Problem Solving",
    ],
    "data_scientist": [
        "Pythonic Fundamentals, Memory Model & Primitives",
        "Asyncio & High-Throughput Asynchronous Python",
        "Neural Networks & Deep Learning Engineering",
        "MLOps: Experiment Tracking, Serving & Monitoring",
        "Data Structures & Algorithmic Problem Solving",
    ],
    "product_manager": [
        "Relational Data Modeling & Advanced SQL Optimization",
        "PRD Specs, Prototyping & Agile Execution",
    ],
}


def catalog_role_ids():
    with open(db.ROLES_JSON_PATH, "r", encoding="utf-8") as f:
        return [role["id"] for role in json.load(f)["roles"]]


def default_choices(role_id):
    schema = tracker_service.ROLE_STACK_SCHEMAS[role_id]
    return [schema[dim]["options"][0] for dim in ("dim1", "dim2", "dim3")]


def default_plan(role_id):
    return tracker_service.build_topics_from_choices(role_id, default_choices(role_id))


# The roles whose stack and syllabus content this module added. The original
# roles keep whatever their shipped stacks produced, including options that never
# mapped to a topic — that is frozen behaviour, not something to "fix" here.
TAILORED_ROLE_IDS = sorted(set(tracker_service.ROLE_STACK_SCHEMAS) - set(ORIGINAL_ROLE_IDS))


def every_stacked_option(role_ids):
    for role_id in role_ids:
        schema = tracker_service.ROLE_STACK_SCHEMAS[role_id]
        for dim in ("dim1", "dim2", "dim3"):
            for option in schema[dim]["options"]:
                yield role_id, option


class StackCoverageTests(unittest.TestCase):
    """A role without a tailored stack silently falls back to a generic syllabus."""

    def test_every_catalogued_role_has_a_tailored_stack(self):
        missing = [role_id for role_id in catalog_role_ids()
                   if role_id not in tracker_service.ROLE_STACK_SCHEMAS]
        self.assertEqual(missing, [], "these roles would fall back to the generic stack")

    def test_no_stack_belongs_to_an_unknown_role(self):
        known = set(catalog_role_ids())
        orphaned = sorted(set(tracker_service.ROLE_STACK_SCHEMAS) - known)
        self.assertEqual(orphaned, [], "a stack for a non-catalogued role can never be reached")

    def test_every_stack_offers_three_dimensions_of_distinct_choices(self):
        for role_id, schema in tracker_service.ROLE_STACK_SCHEMAS.items():
            with self.subTest(role=role_id):
                for dim in ("dim1", "dim2", "dim3"):
                    self.assertTrue(schema[dim]["label"], f"{dim} has no label")
                    options = schema[dim]["options"]
                    self.assertGreaterEqual(len(options), 2, f"{dim} is not really a choice")
                    self.assertEqual(len(options), len(set(options)), f"{dim} repeats an option")


class SyllabusCoverageTests(unittest.TestCase):
    def test_every_tailored_role_has_content_for_each_of_its_options(self):
        """Picking an option that maps to nothing would leave the plan looking broken."""
        for role_id, option in every_stacked_option(TAILORED_ROLE_IDS):
            with self.subTest(role=role_id, option=option):
                self.assertTrue(
                    tracker_service.build_topics_from_choices(role_id, [option]),
                    "this option would produce an empty syllabus",
                )

    def test_every_combination_of_a_tailored_role_yields_a_usable_plan(self):
        for role_id in TAILORED_ROLE_IDS:
            schema = tracker_service.ROLE_STACK_SCHEMAS[role_id]
            dimensions = [schema[dim]["options"] for dim in ("dim1", "dim2", "dim3")]
            for combo in itertools.product(*dimensions):
                with self.subTest(role=role_id, combo=" + ".join(combo)):
                    topics = tracker_service.build_topics_from_choices(role_id, list(combo))
                    names = [t["topic_name"] for t in topics]
                    self.assertGreaterEqual(len(names), 3, "a plan this thin is not worth studying")
                    self.assertEqual(len(names), len(set(names)), "the same topic twice wastes effort")
                    for topic in topics:
                        self.assertTrue(topic["category"] and topic["topic_name"])
                        self.assertGreaterEqual(len(topic["subtopics"]), 3)
                        self.assertTrue(all(s.strip() for s in topic["subtopics"]))
                        self.assertGreater(topic["estimated_hours"], 0)


class SpecialistContentTests(unittest.TestCase):
    """The blocks added for the newer specialisations must hold the same content bar."""

    def test_specialist_blocks_satisfy_the_content_contract(self):
        for keywords, category, name, subtopics, hours in tracker_service._SPECIALIST_SYLLABUS:
            with self.subTest(topic=name):
                self.assertTrue(keywords, "a block with no keyword can never be reached")
                self.assertTrue(all(k.strip() for k in keywords))
                self.assertTrue(category and name)
                self.assertGreaterEqual(len(subtopics), 4)
                self.assertGreater(hours, 0)

    def test_specialist_titles_are_unique(self):
        titles = [name for _, _, name, _, _ in tracker_service._SPECIALIST_SYLLABUS]
        self.assertEqual(len(titles), len(set(titles)), "two blocks would read as the same topic")


class NoRegressionTests(unittest.TestCase):
    """Expanding the syllabus must not rewrite the plans of the original roles."""

    def test_specialist_keywords_cannot_reach_the_original_roles(self):
        original_text = " ".join(
            option.lower()
            for role_id, schema in tracker_service.ROLE_STACK_SCHEMAS.items()
            if role_id in ORIGINAL_ROLE_IDS
            for dim in ("dim1", "dim2", "dim3")
            for option in schema[dim]["options"]
        )

        clashes = sorted({
            keyword
            for keywords, *_ in tracker_service._SPECIALIST_SYLLABUS
            for keyword in keywords
            if keyword in original_text
        })

        self.assertEqual(
            clashes, [],
            "these keywords appear in the original roles' stacks, so they would add "
            "topics to plans candidates may already have progressed on",
        )

    def test_the_original_roles_default_plan_is_unchanged(self):
        for role_id, expected in SHIPPED_PLANS.items():
            with self.subTest(role=role_id):
                actual = [t["topic_name"] for t in default_plan(role_id)]
                self.assertEqual(actual, expected)


class FoundationTopicTests(unittest.TestCase):
    """DSA is added for engineering roles — not for product, business or program tracks."""

    def test_engineering_roles_get_the_foundation_topic(self):
        for role_id in ("backend_dev", "mobile_dev", "game_developer",
                        "embedded_systems_engineer", "penetration_tester"):
            with self.subTest(role=role_id):
                self.assertIn(DSA_TOPIC, [t["topic_name"] for t in default_plan(role_id)])

    def test_non_engineering_tracks_skip_the_foundation_topic(self):
        for role_id in ("product_manager", "business_analyst", "product_designer",
                        "product_analyst", "technical_program_manager"):
            with self.subTest(role=role_id):
                self.assertNotIn(DSA_TOPIC, [t["topic_name"] for t in default_plan(role_id)])


class StackApiTests(unittest.TestCase):
    def test_the_api_serves_the_tailored_stack_for_a_new_role(self):
        for role_id in ("mobile_dev", "product_designer", "technical_program_manager"):
            with self.subTest(role=role_id):
                response = client.get(f"/tracker/stack/{role_id}")
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(set(body), {"dim1", "dim2", "dim3"})
                for dim in ("dim1", "dim2", "dim3"):
                    self.assertGreaterEqual(len(body[dim]["options"]), 2)

    def test_an_unknown_role_still_returns_a_usable_stack(self):
        response = client.get("/tracker/stack/not_a_real_role")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreaterEqual(len(response.json()["dim1"]["options"]), 2)


class TrackerJourneyForATailoredRoleTests(unittest.TestCase):
    """End-to-end: a candidate who picks a newer role gets the tailored plan back."""

    CHOICES = [
        "Design Tokens, Typography & Colour Systems",
        "Usability Testing & User Interviews",
        "Design Ops & Component Libraries",
    ]
    EXPECTED = [
        "Design Tokens, Typography & Colour Systems",
        "Usability Testing & User Interviews",
        "Design Ops, Component Libraries & Contribution",
    ]

    def test_saving_a_tailored_stack_records_the_specialist_syllabus(self):
        headers = signup("Design Candidate")

        response = client.put(
            "/tracker/schedule",
            headers=headers,
            json={
                "role_id": "product_designer",
                "weekday_hours": 2.0,
                "weekend_hours": 4.0,
                "target_languages": self.CHOICES,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        topics = [t["topic_name"] for t in response.json()["topics"]]
        self.assertEqual(sorted(topics), sorted(self.EXPECTED))
        self.assertNotIn(DSA_TOPIC, topics, "a design role should not be handed algorithm drills")

    def test_the_saved_plan_is_returned_again_on_reload(self):
        headers = signup("Design Candidate")
        payload = {
            "role_id": "product_designer",
            "weekday_hours": 2.0,
            "weekend_hours": 4.0,
            "target_languages": self.CHOICES,
        }
        saved = client.put("/tracker/schedule", headers=headers, json=payload)
        self.assertEqual(saved.status_code, 200, saved.text)

        reloaded = client.get("/tracker/topics/product_designer", headers=headers)
        self.assertEqual(reloaded.status_code, 200, reloaded.text)
        self.assertEqual(
            sorted(t["topic_name"] for t in reloaded.json()["topics"]),
            sorted(self.EXPECTED),
            "a reload must not silently rewrite the candidate's syllabus",
        )


if __name__ == "__main__":
    unittest.main()
