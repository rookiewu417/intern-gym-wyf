import pandas as pd
from config import StrategyConfig
from strategy import generate_trades, baseline_mask, improved_mask

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

def test_trade_log_has_required_fields():
    cfg = StrategyConfig()
    trades = generate_trades(_features(), _daily(), MODEL, version="baseline_first_day_momentum_daily", mask=baseline_mask, config=cfg)
    required = {"symbol", "coverage_start", "entry_date", "entry_price", "exit_date", "exit_price",
               "shares", "gross_pnl", "fees", "slippage", "net_pnl", "return", "exit_reason",
               "holding_days", "strategy_version"}
    assert required <= set(trades.columns)
