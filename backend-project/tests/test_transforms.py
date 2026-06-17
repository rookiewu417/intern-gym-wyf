from datetime import datetime, timezone, timedelta

import pandas as pd
from dataclasses import dataclass

from market_state_engine.transforms import (
    ms_to_hk_iso, minute_bar, trade_tick, broker_queue_from_rows, flatten_broker_levels,
    filter_current_day, big_trade_alert, merge_alert, upsert_bar_changed, empty_snapshot,
    latest_daily_volume, trade_date_from_timestamp,
)

HK_TZ = timezone(timedelta(hours=8))


@dataclass
class FakeState:                       # big_trade_alert 鸭子类型只需 symbol/baseline_volume
    symbol: str
    baseline_volume: int


def _hk_ms(year, month, day, hour, minute):
    # 由 datetime 反推 epoch ms，避免硬编码魔数（自洽，不依赖手算）
    return int(datetime(year, month, day, hour, minute, tzinfo=HK_TZ).timestamp() * 1000)


def test_ms_to_hk_iso_localizes_to_plus08():
    iso = ms_to_hk_iso(_hk_ms(2026, 6, 9, 9, 30))         # 13 位毫秒分支
    assert iso.endswith("+08:00")
    assert iso[:10].replace("-", "") == "20260609"
    assert iso.startswith("2026-06-09T09:30")
    # 真实 SDK 形态：10 位 epoch 秒（pandas 3.0 datetime64[us]）也必须正确本地化——
    # 这条专门防止「单测用伪造的毫秒而掩盖了秒级 bug」的回归
    assert trade_date_from_timestamp(ms_to_hk_iso(1780992600)) == "20260609"


def test_minute_bar_from_sdk_payload_only_time_ms():
    # SDK 1m payload 只有 time(epoch 秒/毫秒)；适配层注入 bar_ts 后 minute_bar 应产出 +08:00 时间戳
    ms = _hk_ms(2026, 6, 9, 9, 30)
    row = {"time": ms, "bar_ts": ms_to_hk_iso(ms),
           "open": 350.0, "high": 351.0, "low": 349.0, "close": 350.5, "volume": 1200, "amount": 420000.0}
    bar = minute_bar(row)
    assert bar["timestamp"].endswith("+08:00")
    assert bar["close"] == 350.5 and bar["price"] == 350.5 and bar["volume"] == 1200
    assert trade_date_from_timestamp(bar["timestamp"]) == "20260609"


def test_broker_queue_preserves_sparse_positions_never_renumber():
    # 镜像 test_contracts.py:43-54 —— 1/3/11 不连续，position 与 gear 都要原样保留
    q = broker_queue_from_rows([
        {"side": "ask", "position": 1, "gear": 1, "price": 10.0, "broker_code": "1", "volume": 100, "queue_ts": "2026-06-01T09:30:00+08:00"},
        {"side": "ask", "position": 3, "gear": 3, "price": 10.2, "broker_code": "2", "volume": 200, "queue_ts": "2026-06-01T09:30:00+08:00"},
        {"side": "ask", "position": 11, "gear": 11, "price": 11.0, "broker_code": "3", "volume": 300, "queue_ts": "2026-06-01T09:30:00+08:00"},
    ], {}, effective_day="20260601")
    assert [l["position"] for l in q["ask"]] == [1, 3, 11]
    assert [l["gear"] for l in q["ask"]] == [1, 3, 11]


def test_flatten_then_group_preserves_sdk_gear_and_sums_cells_with_fallback_flags():
    # 对抗评审 blocker-1：LIVE/hydrate 路径（flatten→group）必须保 SDK 派生 gear、档位量=Σcell、且 sourceDate/historical/fallback 正确
    payload = {
        "queue_ts": "2026-06-03T11:29:08.935+08:00",
        "askbrokerqueues": [{"gear": 819, "position": 819, "price": 710.5, "brokers": ["6389", "0"], "volumes": [60, 40]}],
        "bidbrokerqueues": [],
    }
    rows = flatten_broker_levels(payload)
    q = broker_queue_from_rows(rows, {}, effective_day="20260609")
    assert q["ask"][0]["position"] == 819 and q["ask"][0]["gear"] == 819
    assert q["ask"][0]["volume"] == 100 and q["ask"][0]["brokerCount"] == 2
    assert q["ask"][0]["brokers"][1]["displayName"] == "未披露"   # 码 0
    assert q["sourceDate"] == "20260603"
    assert q["historical"] is True and q["fallback"] is True       # 20260603 != 20260609


def test_flatten_is_defensive_on_empty_and_missing():
    assert flatten_broker_levels({"askbrokerqueues": [], "bidbrokerqueues": []}) == []
    # volumes 短于 brokers 时缺失补 0，不抛
    rows = flatten_broker_levels({"queue_ts": "2026-06-01T09:30:00+08:00",
                                  "askbrokerqueues": [{"gear": 5, "price": 10.0, "brokers": ["1", "2"], "volumes": [100]}]})
    assert rows[1]["volume"] == 0 and rows[0]["position"] == 5


def test_big_trade_alert_threshold_truncation_and_fallback():
    s = FakeState("02723.HK", baseline_volume=10_000_000)         # threshold=max(1,int(5000.0))=5000
    tick = {"id": "T1", "timestamp": "2026-06-09T10:00:00+08:00", "tradeDate": "20260609",
            "price": 350.0, "volume": 5000, "turnover": 1.75e6, "side": "buy", "brokerCode": "1234"}
    alert = big_trade_alert(s, tick)
    assert alert["thresholdVolume"] == 5000 and alert["id"] == "big-02723.HK-T1"
    assert alert["sourceDate"] == "20260609" and alert["thresholdRatio"] == 0.0005
    tick_small = {**tick, "volume": 4999}
    assert big_trade_alert(s, tick_small) is None                 # 低于阈值返回 None
    s0 = FakeState("X", baseline_volume=0)                        # baseline<=0 → 硬 fallback 1000
    assert big_trade_alert(s0, {**tick, "volume": 999})  is None
    assert big_trade_alert(s0, {**tick, "volume": 1000})["thresholdVolume"] == 1000


def test_merge_alert_dedup_by_id_and_cap_100():
    alerts = []
    a = {"id": "big-X-1"}
    merge_alert(alerts, a)
    merge_alert(alerts, dict(a))                                   # 同 id 不重复
    assert len(alerts) == 1
    for i in range(120):
        merge_alert(alerts, {"id": f"big-X-{i+2}"})
    assert len(alerts) == 100 and alerts[0]["id"] == "big-X-121"   # newest-first, cap 100


def test_filter_current_day_drops_stale():
    rows = [{"timestamp": "2026-06-09T10:00:00+08:00"}, {"timestamp": "2026-06-08T10:00:00+08:00"}]
    assert filter_current_day(rows, "20260609") == [rows[0]]


def test_upsert_bar_changed_detects_noop():
    bars = []
    bar = {"timestamp": "2026-06-09T09:30:00+08:00", "close": 1.0}
    assert upsert_bar_changed(bars, bar) is True
    assert upsert_bar_changed(bars, dict(bar)) is False           # 完全相同 → no-op
    assert upsert_bar_changed(bars, {**bar, "close": 2.0}) is True


def test_latest_daily_volume_keeps_latest_positive():
    df = pd.DataFrame([
        {"symbol": "02723.HK", "trade_date": 20260520, "volume": 100},
        {"symbol": "02723.HK", "trade_date": 20260521, "volume": 200},
        {"symbol": "X.HK", "trade_date": 20260521, "volume": 0},
    ])
    assert latest_daily_volume(df) == {"02723.HK": 200}
