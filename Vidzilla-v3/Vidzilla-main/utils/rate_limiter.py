"""rate_limiter.py — Per-user rate limiting"""
import time
from collections import defaultdict

class RateLimiter:
    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.requests  = defaultdict(list)
        self.max       = max_requests
        self.window    = window_seconds

    def _clean(self, user_id: int):
        now = time.time()
        self.requests[user_id] = [t for t in self.requests[user_id] if now - t < self.window]

    def is_allowed(self, user_id: int) -> bool:
        self._clean(user_id)
        if len(self.requests[user_id]) >= self.max:
            return False
        self.requests[user_id].append(time.time())
        return True

    def seconds_until_allowed(self, user_id: int) -> int:
        self._clean(user_id)
        if not self.requests[user_id]:
            return 0
        oldest = min(self.requests[user_id])
        return max(0, int(self.window - (time.time() - oldest)))

# 5 requests per minute per user
rate_limiter = RateLimiter(max_requests=5, window_seconds=60)
