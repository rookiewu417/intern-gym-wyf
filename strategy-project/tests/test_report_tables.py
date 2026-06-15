import pandas as pd
from report_tables import comparison_table, sensitivity_table, stratify_by_quantile

def test_comparison_table_lists_versions():
    by_ver = {
        "baseline_first_day_momentum_daily": {"trade_count": 5, "win_rate": 0.4, "total_return": 0.1, "max_drawdown": -100, "average_holding_days": 2.0, "profit_factor": 1.2},
        "improved_grey_market_filter": {"trade_count": 2, "win_rate": 0.5, "total_return": 0.2, "max_drawdown": -50, "average_holding_days": 2.0, "profit_factor": 1.5},
    }
    md = comparison_table(by_ver)
    assert "baseline_first_day_momentum_daily" in md and "improved_grey_market_filter" in md
    assert "trade_count" in md

def test_sensitivity_table_lists_scales():
    rows = {0.5: {"total_return": 0.3}, 1.0: {"total_return": 0.2}, 2.0: {"total_return": 0.0}}
    md = sensitivity_table(rows)
    assert "0.5" in md and "2.0" in md

def test_stratify_by_quantile_groups():
    trades = pd.DataFrame({"return": [0.1, 0.2, -0.1, 0.05], "public_subscription_multiple": [10, 200, 5, 150]})
    out = stratify_by_quantile(trades, "public_subscription_multiple", bins=2)
    assert len(out) >= 1
    assert "count" in out.columns and "avg_return" in out.columns
