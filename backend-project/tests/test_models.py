from market_state_engine.models import frame, SymbolState, DEFAULT_SYMBOLS, DELTA_RING_CAPACITY


def test_frame_source_is_candidate_backend():
    msg = frame("hello", payload={"symbols": ["02723.HK"]})
    assert msg["schema_version"] == 1
    assert msg["protocol"] == "terminal-message-v3"
    assert msg["type"] == "hello"
    assert msg["source"] == "candidate-backend"   # test_contracts.py:62 的同一断言
    assert msg["server_ts"]
    assert msg["payload"]["symbols"] == ["02723.HK"]
    assert "symbol" not in msg and "seq" not in msg and "request_id" not in msg


def test_frame_conditional_fields():
    msg = frame("delta", symbol="02723.HK", seq=5, request_id="r1", payload={"delta_type": "minute_bar"})
    assert msg["symbol"] == "02723.HK"
    assert msg["seq"] == 5
    assert msg["request_id"] == "r1"
    # seq=0 时省略
    assert "seq" not in frame("snapshot", symbol="X", seq=0)


def test_symbol_state_defaults():
    st = SymbolState(symbol="02723.HK", name="深演智能", baseline_volume=1000, effective_day="20260609")
    assert st.seq == 0 and st.base_seq == 0
    assert st.deltas.maxlen == DELTA_RING_CAPACITY
    assert st.last_queue_ts == "" and st.seen_tick_ids == set()
    assert len(DEFAULT_SYMBOLS) == 5
