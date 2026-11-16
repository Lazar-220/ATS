import threading
import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    """Sliding window: at most `rpm` acquisitions in any 60 seconds.

    In-process on purpose. That is correct while one worker process makes every LLM call;
    a second worker would exceed the provider's quota unless the limiter moves into shared
    state (a Postgres row or advisory lock).

    The clock and the sleep are injectable so tests simulate minutes instead of waiting.
    """

    WINDOW_S = 60.0

    def __init__(
        self,
        rpm: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rpm < 1:
            raise ValueError("rpm must be at least 1")
        self._rpm = rpm
        self._clock = clock
        self._sleep = sleep
        self._starts: deque[float] = deque()
        # Held while sleeping: callers queue up in order instead of all waking at once.
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            while True:
                now = self._clock()
                while self._starts and self._starts[0] <= now - self.WINDOW_S:
                    self._starts.popleft()
                if len(self._starts) < self._rpm:
                    self._starts.append(now)
                    return
                self._sleep(self._starts[0] + self.WINDOW_S - now)
