import time

from market_state_engine.adapters.xtquant_adapter import XtquantAdapter
from market_state_engine.transforms import flatten_broker_levels, broker_queue_from_rows, trade_date_from_timestamp
from market_state_engine.models import DEFAULT_SYMBOLS


def test_fetch_latest_queue_payload_retains_queue_ts():
    # 对抗评审 blocker：缺省 field_list 会丢 queue_ts，使 sourceDate 空、fallback 失效
    ad = XtquantAdapter(names={})
    payload = ad.fetch_latest_queue_payload("02723.HK")
    assert payload is not None
    assert payload.get("queue_ts") or payload.get("timestamp")
    rows = flatten_broker_levels(payload)
    q = broker_queue_from_rows(rows, {}, effective_day="20260609")
    assert q["sourceDate"] == "20260603"          # 02723.HK 的队列日
    assert q["historical"] is True and q["fallback"] is True


def test_hkbrokerqueueex_count_one_is_fast_for_default_symbols():
    # 镜像 test_contracts.py:14-20 的性能/数量契约
    ad = XtquantAdapter(names={})
    started = time.perf_counter()
    for symbol in DEFAULT_SYMBOLS:
        payload = ad.fetch_latest_queue_payload(symbol)
        assert payload is not None
    assert time.perf_counter() - started < 3.0


def test_fetch_minute_rows_localized_to_plus08():
    ad = XtquantAdapter(names={})
    rows = ad.fetch_minute_rows("02723.HK", count=60)
    assert rows
    assert all(r.get("bar_ts", "").endswith("+08:00") for r in rows)
    dates = {trade_date_from_timestamp(r["bar_ts"]) for r in rows}
    assert "20260609" in dates                      # 数据跨到 20260609


def test_fetch_daily_baseline_is_zero_via_xtdata_in_lab():
    # 本 lab xtdata 无 1d 周期，应返回 0（baseline 由 BaselineStore 的 CSV 兜底）
    ad = XtquantAdapter(names={})
    assert ad.fetch_daily_baseline("02723.HK") == 0
