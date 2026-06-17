from __future__ import annotations

import collections
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

PROTOCOL = "terminal-message-v3"
SCHEMA_VERSION = 1
SOURCE = "candidate-backend"  # test_contracts.py:62 —— 不可写成参考实现的 internship-mock-feed
DEFAULT_SYMBOLS = ("02723.HK", "02675.HK", "00100.HK", "02513.HK", "06082.HK")
DELTA_RING_CAPACITY = 512  # per-symbol delta 环形缓冲深度；超出则 resume 退化为 snapshot


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def frame(message_type: str, *, symbol: str = "", seq: int = 0, request_id: str = "",
          payload: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA_VERSION,
        "protocol": PROTOCOL,
        "type": message_type,
        "source": SOURCE,
        "server_ts": now_iso(),
        "payload": payload or {},
    }
    if symbol:
        result["symbol"] = symbol
    if seq:
        result["seq"] = seq
    if request_id:
        result["request_id"] = request_id
    return result


@dataclass
class SymbolState:
    symbol: str
    name: str
    baseline_volume: int
    effective_day: str
    seq: int = 0
    base_seq: int = 0                       # 当前 snapshot 反映的 seq；< base_seq 的 delta 已失效
    payload: dict[str, Any] = field(default_factory=dict)
    deltas: "collections.deque[dict]" = field(
        default_factory=lambda: collections.deque(maxlen=DELTA_RING_CAPACITY))
    sub_ids: dict[str, int] = field(default_factory=dict)   # {period: xtdata subscription seq}
    seen_tick_ids: set[str] = field(default_factory=set)    # 回放 wraparound 去重，抑制重复 trade_tick delta
    last_queue_ts: str = ""                                 # 抑制相同 broker_queue 重发
    lock: "threading.Lock" = field(default_factory=threading.Lock)
