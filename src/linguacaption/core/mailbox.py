from __future__ import annotations

from collections import deque
from threading import Condition
from typing import Any


class LatestMailbox:
    """One pending revision per utterance, bounded across utterances.

    Final requests replace partials for the same utterance. On overload the
    oldest pending utterance is evicted explicitly and counted, never replayed
    minutes late. In-flight native inference is allowed to finish.
    """

    def __init__(self, capacity: int = 3) -> None:
        self.capacity = capacity
        self._items: deque[Any] = deque()
        self._condition = Condition()
        self.closed = False
        self.dropped = 0

    def put(self, item: Any) -> None:
        with self._condition:
            if self.closed:
                return
            for i, old in enumerate(self._items):
                if old.utterance == item.utterance:
                    if item.revision >= old.revision:
                        self._items[i] = item
                    self._condition.notify()
                    return
            if len(self._items) >= self.capacity:
                self._items.popleft()
                self.dropped += 1
            self._items.append(item)
            self._condition.notify()

    def get(self) -> Any | None:
        with self._condition:
            self._condition.wait_for(lambda: self.closed or bool(self._items))
            if self.closed:
                return None
            return self._items.popleft()

    def close(self) -> None:
        with self._condition:
            self.closed = True
            self._items.clear()
            self._condition.notify_all()
