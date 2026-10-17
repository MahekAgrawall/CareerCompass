"""Retrieval evaluation harness: the labels must be valid and the maths correct.

The harness's *numbers* depend on the embedding provider, the catalogue and the
network, so they are not asserted here — they come from running
`python -m evals.retrieval_eval` by hand and reading the report. What must hold
on every run, and is tested here, is:

* the label set is well formed and *realistic*: every expected role id exists in
  the catalogue, every interest and skill is an option a candidate could really
  pick, ids are unique, and the set still contains cases the keyword stage cannot
  reach — otherwise the harness could quietly stop measuring the semantic path
  while still printing a confident number;
* the metric arithmetic is right, on ranked lists whose answer is known by hand;
* the whole path runs end to end against a real (local, offline) index, and
  refuses to report rather than invent a score when the index answers nothing.

Isolation (throwaway database and index) comes from `tests.harness`.
"""
import json
import os
import tempfile
import unittest

from tests.harness import IndexBackedTest, client  # noqa: F401  (isolation must load first)

from config import INTEREST_OPTIONS, SKILL_OPTIONS  # noqa: E402
from evals import retrieval_eval  # noqa: E402
from services import career_service, vector_store  # noqa: E402


def _write(payload) -> str:
    """Writes a candidate labels file to a temporary path and returns it."""
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".json", encoding="utf-8", delete=False
    )
    with handle:
        json.dump(payload, handle)
    return handle.name


def _case(case_id: str) -> retrieval_eval.Case:
    for case in retrieval_eval.load_labels().cases:
        if case.id == case_id:
            return case
    raise AssertionError(f"labels.json has no case {case_id!r}")


class LabelSetTest(unittest.TestCase):
    """The labelled set is the harness's measuring instrument; check the instrument."""

    def setUp(self):
        self.labelled = retrieval_eval.load_labels()
        self.roles_by_id = {role["id"]: role for role in career_service.get_all_roles()}

    def test_every_expected_role_exists_in_the_catalogue(self):
        """A typo would look exactly like a permanent recall failure."""
        retrieval_eval.validate_against(self.labelled.cases, self.roles_by_id)

    def test_unknown_role_ids_are_rejected(self):
        with self.assertRaises(ValueError) as caught:
            retrieval_eval.validate_against(
                self.labelled.cases, list(self.roles_by_id)[:5]
            )
        self.assertIn("roles.json is the source of truth", str(caught.exception))

    def test_ids_are_unique_and_every_case_explains_itself(self):
        ids = [case.id for case in self.labelled.cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in self.labelled.cases:
            self.assertTrue(case.note, f"{case.id} has no note explaining the label")
        self.assertGreaterEqual(len(ids), 25, "the label set should not shrink")

    def test_profiles_use_the_real_option_vocabulary(self):
        """Every profile must be one a candidate could submit from the real form."""
        interests = set(INTEREST_OPTIONS)
        skills = set(SKILL_OPTIONS)
        for case in self.labelled.cases:
            self.assertTrue(
                set(case.profile["interests"]) <= interests,
                f"{case.id} has an interest that is not a questionnaire option",
            )
            self.assertTrue(
                set(case.profile.get("current_skills", [])) <= skills,
                f"{case.id} has a skill that is not a questionnaire option",
            )
            self.assertTrue(
                case.profile.get("career_goal", "").strip(),
                f"{case.id} has no career goal, which is the field that carries meaning",
            )

    def test_the_set_still_contains_labels_only_the_index_can_reach(self):
        """If every label were keyword-reachable the harness would prove nothing.

        This is checked with the matcher's own rule rather than an assumption in
        the file, so relabelling a case as "meaning-only" by hand cannot fool it.
        """
        meaning_only = []
        for case in self.labelled.cases:
            reachable = [
                role_id for role_id in case.expect
                if retrieval_eval.keyword_reachable(case.profile, self.roles_by_id[role_id])
            ]
            if len(reachable) < len(case.expect):
                meaning_only.append(case.id)
        self.assertGreaterEqual(
            len(meaning_only), 8,
            f"only {len(meaning_only)} cases exercise semantic recall: {meaning_only}",
        )

    def test_reachability_predicate_matches_the_matcher(self):
        """The keyword-vs-meaning split must come from the real rule, not a copy."""
        role = {"matching_interests": ["devops", "cloud", "infrastructure", "linux"]}
        self.assertTrue(
            retrieval_eval.keyword_reachable(
                {"interests": ["Cloud, DevOps & Linux"]}, role
            )
        )
        self.assertFalse(
            retrieval_eval.keyword_reachable(
                {"interests": ["UI/UX & Frontend Experiences"]}, role
            )
        )

    def test_load_labels_rejects_broken_files(self):
        bad_files = [
            {"cases": []},
            {},
            {"cases": [{"id": "a", "profile": {"interests": ["Python"]}, "expect": []}]},
            {"cases": [{"id": "a", "profile": {"interests": ["Python"]}}]},
            {"cases": [{"id": "", "profile": {"interests": ["Python"]}, "expect": ["x"]}]},
            {"cases": [{"id": "a", "profile": {"interests": []}, "expect": ["x"]}]},
            {
                "cases": [
                    {"id": "a", "profile": {"interests": ["Python"]}, "expect": ["x"]},
                    {"id": "a", "profile": {"interests": ["Python"]}, "expect": ["y"]},
                ]
            },
        ]
        for payload in bad_files:
            path = _write(payload)
            self.addCleanup(os.unlink, path)
            with self.assertRaises(ValueError, msg=f"accepted {payload!r}"):
                retrieval_eval.load_labels(path)


class MetricsTest(unittest.TestCase):
    """The arithmetic, on ranked lists whose answer is known by hand."""

    def test_hit_recall_and_rank(self):
        ranked = ["a", "b", "c", "d"]
        self.assertTrue(retrieval_eval.hit_at_k(ranked, ["c"], 3))
        self.assertFalse(retrieval_eval.hit_at_k(ranked, ["d"], 3))
        self.assertEqual(retrieval_eval.recall_at_k(ranked, ["b", "d"], 2), 0.5)
        self.assertEqual(retrieval_eval.recall_at_k(ranked, ["b", "d"], 4), 1.0)
        self.assertEqual(retrieval_eval.reciprocal_rank(ranked, ["c"], 4), 1 / 3)
        self.assertEqual(retrieval_eval.reciprocal_rank(ranked, ["d"], 3), 0.0)
        self.assertEqual(retrieval_eval.reciprocal_rank(ranked, [], 4), 0.0)
        self.assertEqual(retrieval_eval.recall_at_k(ranked, [], 4), 0.0)

    def test_sweep_measures_the_gate(self):
        # One case. Neighbours a..d at 0.9/0.8/0.5/0.4; 'a' was expected and is
        # reachable by keyword, 'd' is the meaning-only label.
        rows = [([("a", 0.9), ("b", 0.8), ("c", 0.5), ("d", 0.4)], ["a"], ["d"])]
        sweep = retrieval_eval.sweep_thresholds(rows, [0.9, 0.5, 0.45, 0.4])
        by_threshold = {row["threshold"]: row for row in sweep}

        # At 0.9 only 'a' clears: the expected role is kept, the meaning-only one lost.
        self.assertEqual(by_threshold[0.9]["meaning_recall"], 0.0)
        self.assertEqual(by_threshold[0.9]["precision"], 1.0)
        self.assertEqual(by_threshold[0.9]["slots_per_case"], 1.0)
        # At 0.5, 'a', 'b' and 'c' clear: the label is kept, two unlabelled roles are not.
        self.assertEqual(by_threshold[0.5]["precision"], round(1 / 3, 4))
        # At 0.4 everything clears, including the meaning-only label.
        self.assertEqual(by_threshold[0.4]["meaning_recall"], 1.0)
        self.assertEqual(by_threshold[0.4]["meaning_found"], 1)
        self.assertEqual(by_threshold[0.4]["precision"], 0.25)
        self.assertEqual(by_threshold[0.4]["slots_per_case"], 4.0)

    def test_sweep_reports_nothing_rather_than_zero_where_it_cannot_tell(self):
        rows = [([("a", 0.2)], ["a"], [])]
        above = retrieval_eval.sweep_thresholds(rows, [0.9])[0]
        self.assertIsNone(above["meaning_recall"])   # no meaning-only labels at all
        self.assertIsNone(above["precision"])        # nothing cleared the gate
        self.assertIsNone(above["f1"])
        below = retrieval_eval.sweep_thresholds(rows, [0.1])[0]
        self.assertEqual(below["precision"], 1.0)
        self.assertIsNone(below["f1"])               # recall is undefined, so is F1

    def test_best_threshold_prefers_f1_then_recall(self):
        sweep = [
            {"threshold": 0.1, "f1": 0.2, "meaning_recall": 0.9},
            {"threshold": 0.2, "f1": 0.4, "meaning_recall": 0.5},
            {"threshold": 0.3, "f1": 0.4, "meaning_recall": 0.6},
            {"threshold": 0.4, "f1": None, "meaning_recall": 0.0},
        ]
        self.assertEqual(retrieval_eval.best_threshold(sweep), 0.3)  # tie broken by recall
        self.assertIsNone(retrieval_eval.best_threshold([{"f1": None}]))
        self.assertIsNone(retrieval_eval.best_threshold([]))

    def test_f1_is_undefined_without_both_halves(self):
        self.assertIsNone(retrieval_eval._f1(0.0, 0.5))
        self.assertIsNone(retrieval_eval._f1(0.5, 0.0))
        self.assertIsNone(retrieval_eval._f1(None, None))
        self.assertAlmostEqual(retrieval_eval._f1(0.5, 0.5), 0.5)


class HarnessRunTest(IndexBackedTest):
    """The whole path, against a real index built by the offline embedder."""

    def _subset(self):
        return [
            _case("platform_sre"),                 # keyword-reachable, should be found
            _case("meaning_sre_from_frontend"),    # only meaning can reach it
            _case("bi_dashboards_stakeholders"),   # keyword-reachable, different family
        ]

    def test_the_harness_reports_on_a_real_index(self):
        report = retrieval_eval.run_provider(
            "local",
            os.environ["QDRANT_PATH"],
            k=5,
            with_sweep=True,
            wait=0,                      # no sleeping in a unit test
            cases=self._subset(),
        )
        roles = career_service.get_all_roles()
        self.assertEqual(report.case_count, 3)
        self.assertEqual(report.points, len(roles))
        self.assertFalse(report.reused)
        self.assertEqual(report.provider, "local")
        self.assertEqual(report.window, career_service.SEMANTIC_RECALL_LIMIT)
        self.assertEqual(report.configured_floor, career_service.SEMANTIC_FLOOR["local"])

        # The two keyword cases are a fair bar for a working index; the meaning-only
        # case is what the index is for, and the offline embedder can reach its
        # platform family (see the note on that label).
        self.assertEqual(report.hit_at_k, 1.0)
        self.assertEqual(report.window_hit, 1.0)

        # Recall can only ever add to what the keywords found, never remove from it.
        self.assertGreaterEqual(
            report.with_index["served"], report.keyword_only["served"]
        )
        self.assertEqual(report.meaning_cases, 1)
        self.assertGreaterEqual(report.with_index["meaning_slots"], 1)

        # The sweep describes the configured floor, so that row must be present.
        self.assertTrue(report.sweep)
        self.assertIn(
            report.configured_floor, [row["threshold"] for row in report.sweep]
        )
        self.assertTrue(retrieval_eval.format_report(report))
        json.dumps(retrieval_eval.asdict(report))  # the --json path must be serialisable

    def test_the_harness_refuses_to_report_an_empty_index(self):
        """An index that answers nothing is a broken measurement, not a score."""
        original = vector_store.semantic_search
        self.addCleanup(setattr, vector_store, "semantic_search", original)
        vector_store.semantic_search = lambda *args, **kwargs: []
        with self.assertRaises(RuntimeError) as caught:
            retrieval_eval.run_provider(
                "local", os.environ["QDRANT_PATH"], k=5, wait=0, cases=self._subset()
            )
        self.assertIn("broken measurement", str(caught.exception))

    def test_an_existing_index_is_reused_instead_of_rebuilt(self):
        first = retrieval_eval.run_provider(
            "local", os.environ["QDRANT_PATH"], k=5, with_sweep=False, wait=0,
            cases=self._subset(),
        )
        second = retrieval_eval.run_provider(
            "local", os.environ["QDRANT_PATH"], k=5, with_sweep=False, wait=0,
            cases=self._subset(),
        )
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.points, second.points)


if __name__ == "__main__":
    unittest.main()
