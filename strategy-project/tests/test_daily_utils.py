import numpy as np
import pandas as pd
from daily_utils import normalize_daily

def _raw():
    return pd.DataFrame([
        {"symbol": "1.hk", "trade_date": "2026-01-02", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100, "turnover": 1000, "previous_close": 9.8, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260105", "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0, "turnover": 0, "previous_close": 10.5, "suspend_flag": 1},
        {"symbol": "1.HK", "trade_date": "20260106", "open": np.nan, "high": 12, "low": 10, "close": 11, "volume": 50, "turnover": 550, "previous_close": 10.5, "suspend_flag": 0},
    ])

def test_normalize_uppercases_symbol_and_date():
    out = normalize_daily(_raw())
    assert set(out["symbol"]) == {"1.HK"}
    assert out["trade_date"].tolist() == ["20260102", "20260105", "20260106"]

def test_tradable_flags_suspend_zero_volume_and_missing_open():
    out = normalize_daily(_raw()).set_index("trade_date")
    assert bool(out.loc["20260102", "tradable"]) is True
    assert bool(out.loc["20260105", "tradable"]) is False   # suspend + zero volume
    assert bool(out.loc["20260106", "tradable"]) is False   # missing open

def test_missing_prices_not_filled_with_zero():
    out = normalize_daily(_raw()).set_index("trade_date")
    assert pd.isna(out.loc["20260106", "open"])             # 保留 NaN，不填 0
