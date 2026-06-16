import pandas as pd
from download_data import coverage_summary, normalize_universe


def test_normalize_universe_keeps_daily_rows():
    uni = pd.DataFrame({"symbol": ["1.hk"], "name": ["a"], "coverage_start": ["20260102"],
                        "coverage_end": ["20260110"], "daily_rows": [42]})
    out = normalize_universe(uni)
    assert "daily_rows" in out.columns
    assert int(out.iloc[0]["daily_rows"]) == 42

def test_coverage_summary_reports_suspend_and_missing():
    universe = pd.DataFrame({"symbol": ["1.HK", "2.HK"], "name": ["a", "b"],
                             "coverage_start": ["20260102", "20260102"], "coverage_end": ["20260110", "20260110"]})
    daily = pd.DataFrame([
        {"symbol": "1.HK", "trade_date": "20260102", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100, "turnover": 1000, "previous_close": 9, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260105", "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0, "turnover": 0, "previous_close": 10, "suspend_flag": 1},
    ])
    cov = coverage_summary(universe, daily)
    assert cov["symbol_count"] == 2
    assert cov["missing_daily_symbols"] == ["2.HK"]
    assert cov["suspended_rows"] == 1
    assert cov["zero_volume_rows"] == 1
    assert cov["duplicate_daily_keys"] == 0
