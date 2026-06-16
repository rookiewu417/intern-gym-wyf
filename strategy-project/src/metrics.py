from __future__ import annotations

import pandas as pd


def calculate_metrics(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "average_return": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "profit_factor": 0.0,
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "turnover": 0.0,
            "average_holding_days": 0.0,
        }

    # 同一 exit_date 的平局用稳定排序 + 客观次键(entry_date, symbol)定序：让路径依赖的
    # max_drawdown 既与输入行序无关(确定可复现)，又能从交付的 trades.csv 反推一致。
    _tie_keys = [c for c in ("exit_date", "entry_date", "symbol") if c in trades.columns]
    ordered = trades.sort_values(_tie_keys, kind="mergesort") if _tie_keys else trades
    returns = ordered["return"].astype(float)
    pnl = ordered["net_pnl"].astype(float)
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    # 序贯等额下注的复利权益曲线（起点 1.0），total_return / max_drawdown 同源、皆为百分比
    equity = (1.0 + returns).cumprod()
    peak = equity.cummax().clip(lower=1.0)  # 峰值含初始资金 1.0，否则首笔即亏会漏算从起点跌下的回撤
    drawdown = (equity - peak) / peak
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl < 0].sum())
    if "holding_days" in trades.columns:
        holding_days = pd.to_numeric(trades["holding_days"], errors="coerce").fillna(0)
    else:
        holding_days = (
            pd.to_datetime(trades["exit_date"], format="%Y%m%d", errors="coerce")
            - pd.to_datetime(trades["entry_date"], format="%Y%m%d", errors="coerce")
        ).dt.days + 1

    return {
        "trade_count": int(len(trades)),
        "win_rate": float((returns > 0).mean()),
        "average_return": float(returns.mean()),
        "average_win": float(wins.mean()) if not wins.empty else 0.0,
        "average_loss": float(losses.mean()) if not losses.empty else 0.0,
        "profit_factor": (
            float(gross_profit / gross_loss) if gross_loss
            else (float("inf") if gross_profit > 0 else 0.0)
        ),
        "total_return": float(equity.iloc[-1] - 1.0) if not equity.empty else 0.0,
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else 0.0,
        "turnover": float(trades["entry_price"].mul(trades["shares"]).sum()),
        "average_holding_days": float(holding_days.mean()) if not holding_days.empty else 0.0,
    }


def metrics_by_version(trades: pd.DataFrame) -> dict[str, dict[str, float]]:
    if trades.empty or "strategy_version" not in trades.columns:
        return {}
    return {
        str(version): calculate_metrics(group.reset_index(drop=True))
        for version, group in trades.groupby("strategy_version", sort=True)
    }
