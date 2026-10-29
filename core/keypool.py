import threading
import time


class KeyPool:
    """Rotation round-robin avec cooldown par clé."""

    def __init__(self, keys: list[str], cooldown: float = 60.0):
        if not keys:
            raise ValueError("Aucune clé fournie")
        self._keys = list(keys)
        self._cooldown = cooldown
        self._until = {k: 0.0 for k in self._keys}
        self._i = 0
        self._lock = threading.Lock()

    def get(self) -> str | None:
        with self._lock:
            now = time.monotonic()
            for _ in range(len(self._keys)):
                key = self._keys[self._i]
                self._i = (self._i + 1) % len(self._keys)
                if self._until[key] <= now:
                    return key
            return None

    def penalize(self, key: str, seconds: float | None = None) -> None:
        with self._lock:
            self._until[key] = time.monotonic() + (seconds or self._cooldown)

    def wait_time(self) -> float:
        with self._lock:
            return max(0.0, min(self._until.values()) - time.monotonic())
