import os

from market_state_engine.state.engine import MarketStateEngine, BaselineStore
from market_state_engine.adapters.xtquant_adapter import XtquantAdapter


def fresh_engine():
    store = BaselineStore().load()
    engine = MarketStateEngine(["02723.HK"], XtquantAdapter(names=store.names), store)
    engine.hydrate()
    return engine


def push_queue_events(engine, n):
    st = engine.snapshots["02723.HK"]
    eff = st.effective_day
    for i in range(n):
        engine.apply("hkbrokerqueueex", "02723.HK", {
            "queue_ts": f"{eff[:4]}-{eff[4:6]}-{eff[6:]}T10:00:{i:02d}+08:00",
            "askbrokerqueues": [{"gear": 1, "price": 10.0 + i, "brokers": ["1"], "volumes": [100 + i]}],
            "bidbrokerqueues": [],
        })


def test_resume_within_buffer_returns_deltas():
    engine = fresh_engine()
    push_queue_events(engine, 5)
    kind, frames = engine.resume_since("02723.HK", 2)
    assert kind == "deltas"
    assert [f["seq"] for f in frames] == [3, 4, 5]


def test_resume_already_current_returns_empty():
    engine = fresh_engine()
    push_queue_events(engine, 3)
    kind, frames = engine.resume_since("02723.HK", 3)
    assert kind == "deltas" and frames == []


def test_resume_beyond_buffer_returns_snapshot():
    engine = fresh_engine()
    push_queue_events(engine, 600)            # > DELTA_RING_CAPACITY(512)
    kind, frames = engine.resume_since("02723.HK", 1)
    assert kind == "snapshot"
    assert frames and frames[0]["type"] == "snapshot"


def test_seq_never_resets_on_rehydrate_day_switch(monkeypatch):
    engine = fresh_engine()
    push_queue_events(engine, 4)
    st = engine.snapshots["02723.HK"]
    seq_before = st.seq
    # 强制切到另一交易日并重新水合
    monkeypatch.setenv("MARKET_EFFECTIVE_DAY", "20260608")
    engine.hydrate_symbol("02723.HK")
    assert st.seq == seq_before                # seq 单调，绝不回退
    assert st.base_seq == st.seq and len(st.deltas) == 0
    assert st.effective_day == "20260608"
    assert {b["timestamp"][:10].replace("-", "") for b in st.payload["minute_bars"]} == {"20260608"}  # 旧日 bar 已丢
    kind, _ = engine.resume_since("02723.HK", 1)   # 旧 last_seq 落后于 base_seq
    assert kind == "snapshot"
