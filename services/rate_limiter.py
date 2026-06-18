import time


class RateLimiter:
    def __init__(self, cooldown: float):
        self._cooldown = cooldown
        self._last_used: dict[int, float] = {}

    def check(self, user_id: int) -> float:
        """Returns 0.0 if allowed, or seconds remaining if rate limited."""
        now = time.monotonic()
        remaining = self._cooldown - (now - self._last_used.get(user_id, 0))
        if remaining > 0:
            return remaining
        self._last_used[user_id] = now
        return 0.0
