import os

from market_state_engine.state.engine import MarketStateEngine, BaselineStore
from market_state_engine.adapters.xtquant_adapter import XtquantAdapter
from market_state_engine.models import DEFAULT_SYMBOLS
from market_state_engine.transforms import trade_date_from_timestamp


def build_engine(symbols):
    store = BaselineStore().load()
    engine = MarketStateEngine(list(symbols), XtquantAdapter(names=store.names), store)
    engine.hydrate()
    return engine


def test_hydrate_is_warm_with_mock_rows():
    # test_smoke 的强约束：hydrate 后 runtime_state 必须 WARM（不能被 touch_freshness 漏成 LIVE），mock_rows.minute_bars>0
    engine = build_engine(["02723.HK"])
    payload = engine.snapshots["02723.HK"].payload
    assert payload["freshness"]["runtime_state"] == "WARM"
    assert payload["freshness"]["mock_rows"]["minute_bars"] > 0


def test_candidate_snapshot_effective_day_contract():
    # 镜像 test_contracts.py:23-40，但跑在【候选引擎】上（test_contracts 只校验参考实现）
    engine = build_engine(DEFAULT_SYMBOLS)
    for symbol in DEFAULT_SYMBOLS:
        payload = engine.snapshot_frame(symbol)["payload"]
        effective_day = payload["snapshot"]["tradeDate"]
        assert effective_day
        assert payload["freshness"]["effective_day"] == effective_day
        assert {b["timestamp"][:10].replace("-", "") for b in payload["minute_bars"]} == {effective_day}
        assert {a["tradeDate"] for a in payload["alerts"]} <= {effective_day}
        q = payload["broker_queue"]
        assert set(q) >= {"ask", "bid", "sourceDate", "historical", "fallback"}
        if q["sourceDate"] and q["sourceDate"] != effective_day:
            assert q["historical"] is True and q["fallback"] is True


def test_broker_queue_fallback_flags_for_02723():
    engine = build_engine(["02723.HK"])
    q = engine.snapshots["02723.HK"].payload["broker_queue"]
    assert q["sourceDate"] == "20260603"          # 队列日 != effective_day(20260609)
    assert q["historical"] is True and q["fallback"] is True


def test_apply_drops_off_effective_day_event():
    engine = build_engine(["02723.HK"])
    st = engine.snapshots["02723.HK"]
    before = st.seq
    stale = {"time": 0, "bar_ts": "2025-01-01T09:30:00+08:00", "close": 1.0, "open": 1.0, "high": 1.0, "low": 1.0, "volume": 1, "amount": 1.0}
    assert engine.apply("1m", "02723.HK", stale) is None          # 旧日事件被丢
    assert st.seq == before                                       # 不 bump seq


def test_apply_broker_queue_full_overwrite_never_accumulate():
    engine = build_engine(["02723.HK"])
    st = engine.snapshots["02723.HK"]
    eff = st.effective_day
    p1 = {"queue_ts": f"{eff[:4]}-{eff[4:6]}-{eff[6:]}T10:00:00+08:00",
          "askbrokerqueues": [{"gear": 1, "price": 10.0, "brokers": ["1"], "volumes": [100]}], "bidbrokerqueues": []}
    p2 = {"queue_ts": f"{eff[:4]}-{eff[4:6]}-{eff[6:]}T10:00:01+08:00",
          "askbrokerqueues": [{"gear": 2, "price": 10.1, "brokers": ["2"], "volumes": [200]}], "bidbrokerqueues": []}
    engine.apply("hkbrokerqueueex", "02723.HK", p1)
    engine.apply("hkbrokerqueueex", "02723.HK", p2)
    ask = st.payload["broker_queue"]["ask"]
    assert len(ask) == 1 and ask[0]["position"] == 2 and ask[0]["volume"] == 200   # 覆盖，非累加


def test_apply_seq_monotonic_and_suppresses_noop():
    engine = build_engine(["02723.HK"])
    st = engine.snapshots["02723.HK"]
    eff = st.effective_day
    p = {"queue_ts": f"{eff[:4]}-{eff[4:6]}-{eff[6:]}T10:00:00+08:00",
         "askbrokerqueues": [{"gear": 1, "price": 10.0, "brokers": ["1"], "volumes": [100]}], "bidbrokerqueues": []}
    f1 = engine.apply("hkbrokerqueueex", "02723.HK", p)
    s1 = st.seq
    f2 = engine.apply("hkbrokerqueueex", "02723.HK", dict(p))      # 同 queue_ts → no-op
    assert f1["seq"] == s1 and f2 is None and st.seq == s1         # seq 不膨胀
