"""The AI endpoints are budgeted per caller.

The app is guest-friendly on purpose: a visitor can answer the questionnaire,
match and even generate a roadmap without an account. That also means the AI
endpoints are open to anyone with the URL, so they are metered instead. These
tests pin where the meter bites: a hard 429 where the AI *is* the answer, and a
quiet downgrade for `/match`, whose ranked answer never needed the AI to begin
with.

Isolation (throwaway database) comes from `tests.harness`. No test reaches
Gemini: the key is patched away, so the only thing under test is the meter.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.harness import client  # noqa: E402,F401  (throwaway database first)

from app import dependencies  # noqa: E402
from services import ai_service  # noqa: E402
from services.rate_limit import RateLimiter  # noqa: E402


class RateLimiterTests(unittest.TestCase):
    """The window arithmetic, driven by an injected clock rather than sleeps."""

    def test_the_budget_is_spent_call_by_call(self):
        now = [1000.0]
        limiter = RateLimiter(max_calls=2, window_seconds=60, clock=lambda: now[0])

        self.assertEqual(limiter.check("a"), (True, 0.0))
        self.assertTrue(limiter.check("a")[0])

        allowed, retry_after = limiter.check("a")
        self.assertFalse(allowed)
        self.assertAlmostEqual(retry_after, 60.0, places=3)

    def test_the_window_slides(self):
        now = [1000.0]
        limiter = RateLimiter(max_calls=1, window_seconds=60, clock=lambda: now[0])

        self.assertTrue(limiter.check("a")[0])
        self.assertFalse(limiter.check("a")[0])

        now[0] += 61
        self.assertTrue(limiter.check("a")[0], "a freed slot must not stay blocked")

    def test_a_rejected_call_does_not_extend_the_penalty(self):
        now = [0.0]
        limiter = RateLimiter(max_calls=1, window_seconds=60, clock=lambda: now[0])
        limiter.check("a")

        now[0] = 10.0
        _, first = limiter.check("a")
        now[0] = 20.0
        _, second = limiter.check("a")

        # Hammering must not push the retry window further away.
        self.assertLess(second, first)

    def test_each_caller_is_metered_independently(self):
        now = [0.0]
        limiter = RateLimiter(max_calls=1, window_seconds=60, clock=lambda: now[0])

        self.assertTrue(limiter.check("ip:1.2.3.4")[0])
        self.assertFalse(limiter.check("ip:1.2.3.4")[0])
        self.assertTrue(limiter.check("ip:5.6.7.8")[0], "one noisy client must not block another")


class AiQuotaEndpointTests(unittest.TestCase):
    """Over budget: 429 where the whole answer is AI, downgrade where it is not."""

    def setUp(self):
        dependencies.ai_limiter.reset()
        self._original_max = dependencies.ai_limiter.max_calls
        self.addCleanup(self._restore)

    def _restore(self):
        dependencies.ai_limiter.max_calls = self._original_max
        dependencies.ai_limiter.reset()

    def _spend_the_budget(self):
        dependencies.ai_limiter.max_calls = 1

    def test_copilot_and_roadmap_report_429_with_a_retry_after(self):
        self._spend_the_budget()

        # No key: the first (allowed) call fails fast with 503 instead of calling
        # out. The budget is spent either way — the meter runs before the AI work,
        # so neither a missing key nor a model error lets a caller spend for free.
        with mock.patch.object(ai_service, "api_key", ""):
            first = client.post("/chat/stream", json={"role_id": "backend_dev", "new_message": "hi"})
            self.assertEqual(first.status_code, 503, first.text)

            blocked = client.post("/chat/stream", json={"role_id": "backend_dev", "new_message": "hi"})
            self.assertEqual(blocked.status_code, 429, blocked.text)
            self.assertIn("Retry-After", blocked.headers)
            self.assertGreaterEqual(int(blocked.headers["Retry-After"]), 1)

            # The same caller's budget covers every AI endpoint, not one each.
            again = client.post("/roadmap", json={"role_id": "backend_dev", "profile": {}})
            self.assertEqual(again.status_code, 429, again.text)

    def test_match_drops_the_assessment_instead_of_the_answer(self):
        self._spend_the_budget()
        payload = {
            "interests": ["backend systems & databases"],
            "current_skills": ["Java"],
            "explain": True,
        }

        with mock.patch.object(ai_service, "api_key", ""):
            within_budget = client.post("/match", json=payload)
            self.assertEqual(within_budget.status_code, 200, within_budget.text)
            self.assertTrue(within_budget.json()["results"])
            # No key, so the assessment is the deterministic fallback text.
            self.assertTrue(within_budget.json()["explanation"])

            spent = client.post("/match", json=payload)
            self.assertEqual(spent.status_code, 200, "matching must never be blocked by the AI budget")
            self.assertTrue(spent.json()["results"], "the ranked answer still has to come back")
            self.assertEqual(spent.json()["explanation"], "")


if __name__ == "__main__":
    unittest.main()
