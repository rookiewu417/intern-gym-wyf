from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


XTMOCK_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORDING_ROOT = XTMOCK_ROOT / "data" / "recordings" / "xtquant"
DEFAULT_SILVER_ROOT = XTMOCK_ROOT.parent / "sample-data"

REQUIRED_COMPLETE_DATASETS = {
    "depth_snapshot",
    "l2quote_raw",
    "l2thousand_raw",
    "full_tick_raw",
    "hktransaction_raw",
    "hkorder_raw",
    "hkorderaux_raw",
    "instrument_detail_raw",
    "kline_1d_raw",
    "trading_calendar",
}


@dataclass(frozen=True)
class MockConfig:
    recording_root: Path
    silver_root: Path
    run_id: str | None
    replay_mode: str
    replay_speed: float
    replay_max_events_per_subscription: int
    default_market: str


def load_config() -> MockConfig:
    return MockConfig(
        recording_root=Path(os.getenv("XTMOCK_RECORDING_ROOT", str(DEFAULT_RECORDING_ROOT))).resolve(),
        silver_root=Path(os.getenv("XTMOCK_SILVER_ROOT", str(DEFAULT_SILVER_ROOT))).resolve(),
        run_id=os.getenv("XTMOCK_RUN_ID") or None,
        replay_mode=os.getenv("XTMOCK_REPLAY_MODE", "loop"),
        replay_speed=float(os.getenv("XTMOCK_REPLAY_SPEED", "1.0")),
        replay_max_events_per_subscription=max(0, int(os.getenv("XTMOCK_REPLAY_MAX_EVENTS_PER_SUBSCRIPTION", "0") or "0")),
        default_market=os.getenv("XTMOCK_DEFAULT_MARKET", "HK"),
    )
