from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from config import DEFAULT, StrategyConfig
from costs import apply_slippage, trade_cost
from daily_utils import normalize_daily

Mask = Callable[[pd.DataFrame, StrategyConfig], pd.Series]


def baseline_mask(features: pd.DataFrame, config: StrategyConfig) -> pd.Series:
    return features["baseline_signal"].astype(bool)


def reversal_mask(features: pd.DataFrame, config: StrategyConfig) -> pd.Series:
    if "reversal_signal" not in features.columns:
        return pd.Series(False, index=features.index)
    return features["reversal_signal"].astype(bool)


def improved_mask(features: pd.DataFrame, config: StrategyConfig) -> pd.Series:
    base = features["baseline_signal"].astype(bool)
    field = config.grey_filter_field
    if field not in features.columns:
        return pd.Series(False, index=features.index)
    values = pd.to_numeric(features[field], errors="coerce")
    return base & values.notna() & (values >= config.grey_premium_min)


def generate_trades(
    features: pd.DataFrame,
    daily_bars: pd.DataFrame,
    cost_model: dict[str, float],
    *,
    version: str,
    mask: Mask,
    config: StrategyConfig = DEFAULT,
) -> pd.DataFrame:
    bars = normalize_daily(daily_bars)
    selected = features[mask(features, config)]
    trades = []

    for feature in selected.to_dict("records"):
        symbol = str(feature["symbol"])
        entry_date = str(feature["entry_date"])
        symbol_bars = bars[(bars["symbol"] == symbol) & (bars["tradable"])].sort_values("trade_date").reset_index(drop=True)
        entry_matches = symbol_bars[symbol_bars["trade_date"] == entry_date]
        if entry_matches.empty:
            continue
        entry_index = int(entry_matches.index[0])
        path = symbol_bars.iloc[entry_index: entry_index + max(1, config.holding_days)]
        if path.empty:
            continue

        entry_row = path.iloc[0]
        entry_raw = float(entry_row["open"])
        entry_price = apply_slippage(entry_raw, "buy", cost_model)
        shares = int(config.notional_per_trade // entry_price) if entry_price > 0 else 0
        if shares <= 0:
            continue

        exit_row = path.iloc[-1]
        exit_reason = "holding_period"
        exit_raw = float(exit_row["close"])  # 未触发则末个有效交易日 close 出场
        if config.trailing_stop_pct is not None:
            # 追踪止损：止损线=移动高点*(1-trail)、只上移；进入当日用截至昨日的高点判触发，
            # 收盘后才更新高点 → 不会用当日 high 抬线又用当日 low 判触发（无日内未来函数）
            trail = config.trailing_stop_pct
            hwm = entry_price
            for _, row in path.iterrows():
                trail_line = hwm * (1 - trail)
                if float(row["low"]) <= trail_line:
                    exit_row, exit_reason, exit_raw = row, "trailing_stop", min(trail_line, float(row["open"]))
                    break
                hwm = max(hwm, float(row["high"]))
        else:
            stop_level = entry_price * (1 - config.stop_loss_pct)
            take_level = entry_price * (1 + config.take_profit_pct)
            for _, row in path.iterrows():
                # 触发即在触发价位成交；若当日跳空已越过触发价，则按 open 成交（真实可得价）
                day_open = float(row["open"])
                if float(row["low"]) <= stop_level:
                    exit_row, exit_reason, exit_raw = row, "stop_loss", min(stop_level, day_open)
                    break
                if float(row["high"]) >= take_level:
                    exit_row, exit_reason, exit_raw = row, "take_profit", max(take_level, day_open)
                    break
        held_days = int(path[path["trade_date"] <= str(exit_row["trade_date"])].shape[0])

        exit_price = apply_slippage(exit_raw, "sell", cost_model)
        buy_notional = entry_price * shares
        sell_notional = exit_price * shares
        fees = trade_cost(buy_notional, "buy", cost_model) + trade_cost(sell_notional, "sell", cost_model)
        gross_pnl = sell_notional - buy_notional
        slippage = abs(entry_price - entry_raw) * shares + abs(exit_raw - exit_price) * shares
        net_pnl = gross_pnl - fees

        trades.append({
            "symbol": symbol,
            "coverage_start": str(feature.get("coverage_start") or ""),
            "entry_date": str(entry_row["trade_date"]),
            "entry_price": entry_price,
            "exit_date": str(exit_row["trade_date"]),
            "exit_price": exit_price,
            "shares": shares,
            "gross_pnl": gross_pnl,
            "fees": fees,
            "slippage": slippage,
            "net_pnl": net_pnl,
            "return": net_pnl / buy_notional if buy_notional else 0.0,
            "exit_reason": exit_reason,
            "holding_days": held_days,
            "strategy_version": version,
        })

    return pd.DataFrame(trades)


def generate_baseline_trades(features, daily_bars, cost_model, *, notional_per_trade=100_000.0,
                             holding_days=3, stop_loss_pct=0.08, take_profit_pct=0.20):
    """向后兼容包装（scaffold 旧测试用）。"""
    cfg = StrategyConfig(notional_per_trade=notional_per_trade, holding_days=holding_days,
                         stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct)
    return generate_trades(features, daily_bars, cost_model,
                           version="baseline_first_day_momentum_daily", mask=baseline_mask, config=cfg)
