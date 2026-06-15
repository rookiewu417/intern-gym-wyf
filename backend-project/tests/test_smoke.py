from market_state_engine.app import MarketStateEngine


def test_engine_hydrates_mock_rows():
    engine = MarketStateEngine(["02723.HK"])
    engine.hydrate()
    snapshot = engine.snapshots["02723.HK"].payload
    assert snapshot["freshness"]["runtime_state"] == "WARM"
    assert snapshot["freshness"]["mock_rows"]["minute_bars"] > 0

