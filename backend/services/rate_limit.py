"""A tiny in-process rate limiter for the endpoints that spend AI quota.

The roadmap, the copilot and the match explanation all call Gemini, and this app
is deliberately open to guests — so the abuse surface is "anyone with the URL",
not "anyone with an account". Requiring sign-in would break the anonymous-first
flow (a guest can answer the questionnaire, match and generate a roadmap), so the
AI endpoints are *budgeted* per caller instead, and only the AI work is refused.

Deliberately dependency-free and single-process: two workers each keep their own
counters, so the effective limit is per worker. That is enough to stop one client
from draining a quota; a shared store (Redis) would be the next step if the API
were ever run behind more than one process.
"""
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Tuple


class RateLimiter:
    """Sliding-window counter: at most ``max_calls`` per ``window_seconds`` per key.

    ``clock`` is injectable so tests can advance time instead of sleeping.
    """

    def __init__(
        self,
        max_calls: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_calls = max(1, int(max_calls))
        self.window_seconds = float(window_seconds)
        self._clock = clock
        self._calls: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str) -> Tuple[bool, float]:
        """Records one call for ``key``.

        Returns ``(True, 0.0)`` when the call is within budget, otherwise
        ``(False, retry_after)`` where ``retry_after`` is how many seconds until a
        slot frees up. A rejected call is *not* recorded, so a client that keeps
        hammering does not keep extending its own penalty.
        """
        now = self._clock()
        calls = self._calls[key]
        cutoff = now - self.window_seconds
        while calls and calls[0] <= cutoff:
            calls.popleft()

        if len(calls) >= self.max_calls:
            return False, max(0.0, calls[0] + self.window_seconds - now)

        calls.append(now)
        return True, 0.0

    def reset(self) -> None:
        """Forgets every recorded call. Used by tests, and after a config change."""
        self._calls.clear()
