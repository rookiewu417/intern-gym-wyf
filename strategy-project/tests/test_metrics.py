import math

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

def _seq_trades():
    # exit_date 递增；returns = +0.1, -0.2, +0.05
    return pd.DataFrame([
        {"return": 0.1, "net_pnl": 100, "entry_price": 10, "shares": 10, "exit_date": "20260106", "entry_date": "20260105", "holding_days": 1},
        {"return": -0.2, "net_pnl": -200, "entry_price": 10, "shares": 10, "exit_date": "20260107", "entry_date": "20260105", "holding_days": 1},
        {"return": 0.05, "net_pnl": 50, "entry_price": 10, "shares": 10, "exit_date": "20260108", "entry_date": "20260105", "holding_days": 1},
    ])


def test_total_return_is_compounded():
    m = calculate_metrics(_seq_trades())
    expected = 1.1 * 0.8 * 1.05 - 1.0  # 序贯复利，非逐笔之和(-0.05)
    assert abs(m["total_return"] - expected) < 1e-9


def test_max_drawdown_is_percentage():
    m = calculate_metrics(_seq_trades())
    # equity=[1.1,0.88,0.924], peak=1.1 → 最深回撤 (0.88-1.1)/1.1 = -0.2
    assert abs(m["max_drawdown"] - (-0.2)) < 1e-9


def test_max_drawdown_counts_drop_from_initial_capital():
    # 首笔即亏 10%：回撤须相对初始资金 1.0 计（-0.1），不能因 cummax 从首笔之后起算而漏掉
    losing_first = pd.DataFrame([
        {"return": -0.1, "net_pnl": -100, "entry_price": 10, "shares": 10, "exit_date": "20260106", "entry_date": "20260105", "holding_days": 1},
    ])
    m = calculate_metrics(losing_first)
    assert abs(m["max_drawdown"] - (-0.1)) < 1e-9


def test_max_drawdown_deterministic_under_same_exit_date_ties():
    # 同一 exit_date 上一赢一输、其后再一笔：输入行序不应改变 max_drawdown。
    # 稳定排序 + 次键 (exit_date, entry_date, symbol)：赢家 00001 按 symbol 升序排在输家 00002 前。
    rows = [
        {"return": 1.0, "net_pnl": 1000, "entry_price": 10, "shares": 10, "exit_date": "20260101", "entry_date": "20260101", "symbol": "00001.HK", "holding_days": 1},
        {"return": -0.5, "net_pnl": -500, "entry_price": 10, "shares": 10, "exit_date": "20260101", "entry_date": "20260101", "symbol": "00002.HK", "holding_days": 1},
        {"return": -0.5, "net_pnl": -500, "entry_price": 10, "shares": 10, "exit_date": "20260102", "entry_date": "20260101", "symbol": "00003.HK", "holding_days": 1},
    ]
    base = calculate_metrics(pd.DataFrame(rows))
    shuffled = calculate_metrics(pd.DataFrame([rows[1], rows[0], rows[2]]))
    assert base["max_drawdown"] == shuffled["max_drawdown"]  # 确定性：与输入行序无关
    # 赢家先(00001<00002): equity=[2.0, 1.0, 0.5], peak=2.0 → 最深 (0.5-2.0)/2.0 = -0.75
    assert abs(base["max_drawdown"] - (-0.75)) < 1e-9


def test_profit_factor_infinite_when_no_losses():
    all_wins = pd.DataFrame([
        {"return": 0.1, "net_pnl": 100, "entry_price": 10, "shares": 10, "exit_date": "20260106", "entry_date": "20260105", "holding_days": 1},
        {"return": 0.2, "net_pnl": 200, "entry_price": 10, "shares": 10, "exit_date": "20260107", "entry_date": "20260105", "holding_days": 1},
    ])
    m = calculate_metrics(all_wins)
    assert math.isinf(m["profit_factor"]) and m["profit_factor"] > 0


def test_metrics_by_version_splits():
    out = metrics_by_version(_trades())
    assert set(out) == {"baseline_first_day_momentum_daily", "improved_grey_market_filter"}
    assert out["improved_grey_market_filter"]["trade_count"] == 1
    assert out["baseline_first_day_momentum_daily"]["trade_count"] == 2
