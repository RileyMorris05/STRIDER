from __future__ import annotations

from time import monotonic


class RateLimiter:
    def __init__(self, rate_hz: float) -> None:
        if rate_hz <= 0:
            raise ValueError("rate_hz must be positive")
        self._period_s = 1.0 / rate_hz
        self._next_send_s = 0.0

    def ready(self, now_s: float | None = None) -> bool:
        now = monotonic() if now_s is None else now_s
        if now < self._next_send_s:
            return False
        self._next_send_s = now + self._period_s
        return True
