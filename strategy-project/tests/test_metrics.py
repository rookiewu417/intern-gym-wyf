import pandas as pd
from metrics import calculate_metrics, metrics_by_version

def _trades():
    return pd.DataFrame([
        {"strategy_version": "baseline_first_day_momentum_daily", "return": 0.1, "net_pnl": 100, "entry_price": 10, "shares": 10, "exit_date": "20260106", "entry_date": "20260105", "holding_days": 1},
        {"strategy_version": "baseline_first_day_momentum_daily", "return": -0.05, "net_pnl": -50, "entry_price": 10, "shares": 10, "exit_date": "20260108", "entry_date": "20260105", "holding_days": 3},
        {"strategy_version": "improved_grey_market_filter", "return": 0.2, "net_pnl": 200, "entry_price": 10, "shares": 10, "exit_date": "20260106", "entry_date": "20260105", "holding_days": 1},
    ])

def test_drawdown_uses_exit_date_order():
    m = calculate_metrics(_trades())
    assert m["trade_count"] == 3
    assert m["max_drawdown"] <= 0

def test_metrics_by_version_splits():
    out = metrics_by_version(_trades())
    assert set(out) == {"baseline_first_day_momentum_daily", "improved_grey_market_filter"}
    assert out["improved_grey_market_filter"]["trade_count"] == 1
    assert out["baseline_first_day_momentum_daily"]["trade_count"] == 2
