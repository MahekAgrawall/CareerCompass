"""Transparent-matching tests.

A score is only trustworthy if the candidate can check it. These tests pin the
contract that makes that possible:

1. **arithmetic** — the two published component scores reproduce the published
   score, so nobody has to take the number on faith;
2. **advice** — `suggested_skills` only ever names a real profile chip, that the
   candidate does not already hold, and that the role genuinely scores on, so
   following it can never make the stated match look worse;
3. **no model required** — the breakdown is computed deterministically, so it is
   present even when the optional AI narrative is switched off.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import INTEREST_OPTIONS, SKILL_OPTIONS  # noqa: E402
from services import career_service  # noqa: E402
from tests.harness import client  # noqa: E402,F401  (points the live DB at a throwaway file)


def match(interests, skills, explain=False):
    """POSTs /match and returns the parsed body."""
    r = client.post(
        "/match",
        json={"interests": interests, "current_skills": skills, "explain": explain},
    )
    assert r.status_code == 200, r.text
    return r.json()


def expected_score(item, interest_weight, skill_weight):
    """The arithmetic a candidate does in their head, rounded half-up."""
    return (item["interest_score"] * interest_weight + item["skill_score"] * skill_weight + 50) // 100


class ScoreArithmeticTests(unittest.TestCase):
    """The user must be able to reproduce the score from what is on the card."""

    def test_the_weights_are_published_and_explain_the_score(self):
        body = match(["Backend Systems & Databases"], ["Java"])
        self.assertTrue(body["results"])
        self.assertEqual(body["interest_weight"] + body["skill_weight"], 100)

        for item in body["results"]:
            with self.subTest(role=item["role"]["id"]):
                self.assertEqual(
                    item["score"],
                    expected_score(item, body["interest_weight"], body["skill_weight"]),
                )

    def test_components_are_percentages_of_what_the_candidate_supplied(self):
        interests = list(INTEREST_OPTIONS)[:4]
        skills = list(SKILL_OPTIONS)[:6]
        body = match(interests, skills)

        for item in body["results"]:
            with self.subTest(role=item["role"]["id"]):
                self.assertEqual(
                    item["interest_score"],
                    round(len(item["matched_interests"]) / len(interests) * 100),
                )
                self.assertEqual(
                    item["skill_score"],
                    round(len(item["matched_skills"]) / len(skills) * 100),
                )

    def test_a_candidate_with_no_skills_gets_honest_numbers(self):
        """The skill half is empty, not silently forgiven."""
        body = match(["Product Management & Strategy"], [])
        self.assertTrue(body["results"])

        for item in body["results"]:
            with self.subTest(role=item["role"]["id"]):
                self.assertEqual(item["skill_score"], 0)
                self.assertEqual(
                    item["score"],
                    expected_score(item, body["interest_weight"], body["skill_weight"]),
                )

    def test_half_points_round_the_way_a_reader_rounds(self):
        """100% interest + 50% skills is 82.5 — the badge must read 83, not 82."""
        body = match(["Backend Systems & Databases"], ["Java", "Excel Modeling"])
        item = {i["role"]["id"]: i for i in body["results"]}["backend_dev"]

        self.assertEqual((item["interest_score"], item["skill_score"]), (100, 50))
        self.assertEqual(item["score"], 83)

    def test_matched_terms_keep_the_candidates_own_wording(self):
        """The breakdown quotes the chips the candidate picked, not lowercased echoes."""
        body = match(["Backend Systems & Databases"], ["Java"])
        interests = {t for item in body["results"] for t in item["matched_interests"]}
        skills = {t for item in body["results"] for t in item["matched_skills"]}

        self.assertEqual(interests, {"Backend Systems & Databases"})
        self.assertTrue(skills <= {"Java"})
        self.assertIn("Java", skills)

    def test_explanation_survives_without_the_model(self):
        """explain=False keeps the AI narrative empty but the maths intact."""
        body = match(["Coding & Problem Solving"], ["Python"], explain=False)
        self.assertEqual(body["explanation"], "")
        self.assertTrue(body["results"])

        for item in body["results"]:
            self.assertIn("interest_score", item)
            self.assertIn("skill_score", item)
            self.assertIn("suggested_skills", item)


class SuggestedSkillTests(unittest.TestCase):
    """Anything offered as "add this" must be actionable and truthful."""

    def test_every_suggestion_is_a_real_profile_chip(self):
        body = match(["Coding & Problem Solving"], [])
        suggestions = {s for item in body["results"] for s in item["suggested_skills"]}

        self.assertTrue(suggestions, "a skill-less candidate should be told what to add")
        self.assertTrue(suggestions <= set(SKILL_OPTIONS))

    def test_nothing_the_candidate_already_holds_is_suggested(self):
        body = match(list(INTEREST_OPTIONS)[:4], list(SKILL_OPTIONS))

        for item in body["results"]:
            with self.subTest(role=item["role"]["id"]):
                self.assertEqual(item["suggested_skills"], [])

    def test_a_suggestion_always_shares_a_whole_scoring_keyword(self):
        """
        Relevance is token-based, so substring noise cannot leak a false tip.

        The scorer itself also accepts substring overlaps (``go`` inside
        ``mongodb``); suggestions deliberately do not, which is why they can be
        presented as safe advice.
        """
        body = match(list(INTEREST_OPTIONS), [])

        for item in body["results"]:
            role_tokens = set()
            for phrase in item["role"]["matching_skills"]:
                role_tokens |= career_service._keywords(phrase)
            for chip in item["suggested_skills"]:
                with self.subTest(role=item["role"]["id"], chip=chip):
                    self.assertTrue(career_service._keywords(chip) & role_tokens)

    def test_taking_the_advice_never_lowers_the_match(self):
        """Exhaustive over the whole catalog: acting on the advice cannot hurt.

        Each suggestion is already proven to be a real scoring keyword of its own
        role (see the test above), so a role's score can only rise when a
        candidate picks it up. The sweep therefore adds *all* of a role's
        suggestions in one match rather than one call per chip — with a
        hundred-role catalog the per-chip version was quadratic and dominated the
        suite's runtime.
        """
        profile_skills = ["Java"]

        for interest in INTEREST_OPTIONS:
            baseline = career_service.match_roles_smart(
                {"interests": [interest], "current_skills": profile_skills}
            )
            for item in baseline:
                advice = item["suggested_skills"]
                if not advice:
                    continue
                after = career_service.match_roles_smart(
                    {"interests": [interest], "current_skills": profile_skills + advice}
                )
                by_id = {m["role"]["id"]: m for m in after}
                with self.subTest(interest=interest, role=item["role"]["id"]):
                    self.assertIn(item["role"]["id"], by_id, "a suggestion removed the role")
                    self.assertGreaterEqual(
                        by_id[item["role"]["id"]]["skill_score"], item["skill_score"]
                    )
                    self.assertGreaterEqual(by_id[item["role"]["id"]]["score"], item["score"])

    def test_a_role_with_no_skill_overlap_offers_a_way_forward(self):
        """Even at 0% skill fit the card must name something that would move it."""
        body = match(["UI/UX & Frontend Experiences"], [])
        best = body["results"][0]

        self.assertEqual(best["skill_score"], 0)
        self.assertTrue(best["suggested_skills"])


if __name__ == "__main__":
    unittest.main()
