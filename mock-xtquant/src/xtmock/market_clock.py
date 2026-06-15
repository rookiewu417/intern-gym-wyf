from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class ClockFrame:
    dataset: str
    symbol: str
    index: int
    event_time: int | None = None


class ReplayClock:
    def __init__(self):
        self._lock = threading.Lock()
        self._frames: dict[str, ClockFrame] = {}

    def mark_current(
        self,
        dataset: str,
        symbol: str,
        index: int,
        event_time: int | None = None,
    ) -> None:
        with self._lock:
            self._frames[_normalize_symbol(symbol)] = ClockFrame(
                dataset=dataset,
                symbol=symbol,
                index=index,
                event_time=event_time,
            )

    def current(self, symbol: str) -> ClockFrame | None:
        with self._lock:
            return self._frames.get(_normalize_symbol(symbol))

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()


_CLOCK = ReplayClock()


def get_replay_clock() -> ReplayClock:
    return _CLOCK


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()
