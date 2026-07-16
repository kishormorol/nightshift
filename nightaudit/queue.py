"""Persistent round-robin over ``(project, task)`` pairs.

Position is stored as the *last pair served* rather than an index, so that
editing the config — adding a project, reordering tasks — degrades gracefully
instead of silently skipping work.
"""

from __future__ import annotations

from pathlib import Path

from nightaudit.config import state_dir
from nightaudit.store import read_json, write_json

Pair = tuple[str, str]


def queue_path() -> Path:
    return state_dir() / "queue.json"


class Queue:
    def __init__(self, path: Path | None = None):
        self.path = path or queue_path()
        self._last: Pair | None = self._load()

    def _load(self) -> Pair | None:
        raw = read_json(self.path, default={})
        if not isinstance(raw, dict):
            return None
        last = raw.get("last")
        if (
            isinstance(last, list)
            and len(last) == 2
            and all(isinstance(x, str) for x in last)
        ):
            return (last[0], last[1])
        return None

    @property
    def last(self) -> Pair | None:
        return self._last

    def peek(self, pairs: list[Pair]) -> Pair | None:
        """The pair that :meth:`pop` would return, without advancing."""
        if not pairs:
            return None
        if self._last is None or self._last not in pairs:
            # Unknown position (first run, or the last pair was removed from
            # config) — restart from the top rather than guessing.
            return pairs[0]
        return pairs[(pairs.index(self._last) + 1) % len(pairs)]

    def take(self, pair: Pair) -> None:
        """Record ``pair`` as served, wherever it sits in the rotation.

        For when the pair the rotation offered could not run — a project pinned
        to a provider that is out of budget — and a later one was served in its
        place. The passed-over pair is not held back for next time; it simply
        comes round again. Holding it would let one unavailable provider wedge
        the rotation, which is the same starvation :meth:`pop` refuses.
        """
        self._last = pair
        write_json(self.path, {"last": list(pair)})

    def pop(self, pairs: list[Pair]) -> Pair | None:
        """Take the next pair and persist the new position.

        The position advances even when the run later fails: a project that
        always errors must not wedge the rotation and starve the others.
        """
        pair = self.peek(pairs)
        if pair is None:
            return None
        self.take(pair)
        return pair

    def rotation(self, pairs: list[Pair]) -> list[Pair]:
        """``pairs`` reordered to start where :meth:`peek` points.

        Every pair, exactly once, in the order the rotation would offer them —
        so a caller can walk forward looking for one it is able to run.
        """
        start = self.peek(pairs)
        if start is None:
            return []
        i = pairs.index(start)
        return pairs[i:] + pairs[:i]

    def reset(self) -> None:
        self._last = None
        write_json(self.path, {})
