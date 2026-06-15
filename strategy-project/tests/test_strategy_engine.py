import pandas as pd
from config import StrategyConfig
from strategy import generate_trades, baseline_mask, improved_mask, reversal_mask

def _features():
    return pd.DataFrame([
        {"symbol": "1.HK", "coverage_start": "20260102", "entry_date": "20260105",
         "baseline_signal": True, "grey_change_pct": 0.2, "premium_to_ipo_price": 0.2},
        {"symbol": "2.HK", "coverage_start": "20260102", "entry_date": "20260105",
         "baseline_signal": True, "grey_change_pct": -0.1, "premium_to_ipo_price": -0.1},
    ])

def _daily():
    rows = []
    for sym in ("1.HK", "2.HK"):
        rows += [
            {"symbol": sym, "trade_date": "20260105", "open": 100, "high": 105, "low": 99, "close": 102, "volume": 10, "turnover": 1, "previous_close": 100, "suspend_flag": 0},
            {"symbol": sym, "trade_date": "20260106", "open": 102, "high": 108, "low": 101, "close": 107, "volume": 10, "turnover": 1, "previous_close": 102, "suspend_flag": 0},
            {"symbol": sym, "trade_date": "20260107", "open": 107, "high": 110, "low": 104, "close": 109, "volume": 10, "turnover": 1, "previous_close": 107, "suspend_flag": 0},
        ]
    return pd.DataFrame(rows)

MODEL = {"buy_cost_bps": 12.0, "sell_cost_bps": 22.0, "slippage_bps": 10.0, "min_fee": 5.0}

def test_holding_days_bounded_by_window():
    cfg = StrategyConfig(holding_days=3, stop_loss_pct=0.5, take_profit_pct=0.5)
    trades = generate_trades(_features(), _daily(), MODEL, version="baseline_first_day_momentum_daily", mask=baseline_mask, config=cfg)
    assert (trades["holding_days"] <= 3).all()
    assert set(trades["strategy_version"]) == {"baseline_first_day_momentum_daily"}

def test_improved_mask_filters_negative_grey():
    cfg = StrategyConfig(grey_filter_field="grey_change_pct", grey_premium_min=0.0)
    trades = generate_trades(_features(), _daily(), MODEL, version="improved_grey_market_filter", mask=improved_mask, config=cfg)
    assert set(trades["symbol"]) == {"1.HK"}  # 2.HK 暗盘为负被过滤

def _single(*, high, low, close):
    feats = pd.DataFrame([{"symbol": "1.HK", "coverage_start": "20260102", "entry_date": "20260106",
                           "baseline_signal": True}])
    daily = pd.DataFrame([
        {"symbol": "1.HK", "trade_date": "20260105", "open": 100, "high": 105, "low": 99, "close": 102, "volume": 10, "turnover": 1, "previous_close": 100, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260106", "open": 100, "high": high, "low": low, "close": close, "volume": 10, "turnover": 1, "previous_close": 102, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260107", "open": close, "high": close, "low": close, "close": close, "volume": 10, "turnover": 1, "previous_close": close, "suspend_flag": 0},
    ])
    return feats, daily


def test_take_profit_fills_at_take_level():
    # day2 high 触发止盈：成交价应为 take_level（含卖出滑点），而非当日 close
    feats, daily = _single(high=130, low=99, close=125)
    trades = generate_trades(feats, daily, MODEL, version="baseline_first_day_momentum_daily", mask=baseline_mask, config=StrategyConfig())
    row = trades.iloc[0]
    entry_price = 100 * (1 + MODEL["slippage_bps"] / 1e4)
    expected = entry_price * 1.20 * (1 - MODEL["slippage_bps"] / 1e4)
    assert row["exit_reason"] == "take_profit"
    assert abs(row["exit_price"] - expected) < 1e-6


def test_stop_loss_fills_at_stop_level():
    # day2 low 触发止损：成交价应为 stop_level（含卖出滑点），而非当日 close
    feats, daily = _single(high=110, low=80, close=85)
    trades = generate_trades(feats, daily, MODEL, version="baseline_first_day_momentum_daily", mask=baseline_mask, config=StrategyConfig())
    row = trades.iloc[0]
    entry_price = 100 * (1 + MODEL["slippage_bps"] / 1e4)
    expected = entry_price * (1 - 0.08) * (1 - MODEL["slippage_bps"] / 1e4)
    assert row["exit_reason"] == "stop_loss"
    assert abs(row["exit_price"] - expected) < 1e-6


def _with_gap_day3(open3, high3, low3, close3):
    feats = pd.DataFrame([{"symbol": "1.HK", "coverage_start": "20260102", "entry_date": "20260106",
                           "baseline_signal": True}])
    daily = pd.DataFrame([
        {"symbol": "1.HK", "trade_date": "20260105", "open": 100, "high": 105, "low": 99, "close": 102, "volume": 10, "turnover": 1, "previous_close": 100, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260106", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10, "turnover": 1, "previous_close": 102, "suspend_flag": 0},  # entry，不触发
        {"symbol": "1.HK", "trade_date": "20260107", "open": open3, "high": high3, "low": low3, "close": close3, "volume": 10, "turnover": 1, "previous_close": 100, "suspend_flag": 0},
    ])
    return feats, daily


def test_stop_loss_gap_down_fills_at_open():
    # day3 跳空低开击穿止损：实际只能在 open 成交（< stop_level），不能假装在 stop_level
    feats, daily = _with_gap_day3(open3=80, high3=82, low3=78, close3=80)
    trades = generate_trades(feats, daily, MODEL, version="baseline_first_day_momentum_daily", mask=baseline_mask, config=StrategyConfig())
    row = trades.iloc[0]
    assert row["exit_reason"] == "stop_loss"
    expected = 80 * (1 - MODEL["slippage_bps"] / 1e4)
    assert abs(row["exit_price"] - expected) < 1e-6


def test_take_profit_gap_up_fills_at_open():
    # day3 跳空高开越过止盈：实际在 open 成交（> take_level）
    feats, daily = _with_gap_day3(open3=130, high3=135, low3=128, close3=132)
    trades = generate_trades(feats, daily, MODEL, version="baseline_first_day_momentum_daily", mask=baseline_mask, config=StrategyConfig())
    row = trades.iloc[0]
    assert row["exit_reason"] == "take_profit"
    expected = 130 * (1 - MODEL["slippage_bps"] / 1e4)
    assert abs(row["exit_price"] - expected) < 1e-6


def test_reversal_mask_selects_only_reversal_signal():
    feats = pd.DataFrame([
        {"symbol": "1.HK", "coverage_start": "20260102", "entry_date": "20260106", "baseline_signal": False, "reversal_signal": True},
        {"symbol": "2.HK", "coverage_start": "20260102", "entry_date": "20260106", "baseline_signal": True, "reversal_signal": False},
    ])
    trades = generate_trades(feats, _daily(), MODEL, version="reversal_first_day_daily", mask=reversal_mask, config=StrategyConfig())
    assert set(trades["symbol"]) == {"1.HK"}  # 只选 reversal_signal=True，与 momentum 互斥


def test_trade_log_has_required_fields():
    cfg = StrategyConfig()
    trades = generate_trades(_features(), _daily(), MODEL, version="baseline_first_day_momentum_daily", mask=baseline_mask, config=cfg)
    required = {"symbol", "coverage_start", "entry_date", "entry_price", "exit_date", "exit_price",
               "shares", "gross_pnl", "fees", "slippage", "net_pnl", "return", "exit_reason",
               "holding_days", "strategy_version"}
    assert required <= set(trades.columns)
