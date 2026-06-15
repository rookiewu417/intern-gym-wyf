from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无显示环境，必须在 pyplot 之前
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


def _equity(ax, trades: pd.DataFrame, label: str) -> None:
    if trades.empty:
        return
    ordered = trades.sort_values("exit_date")
    equity = ordered["net_pnl"].astype(float).cumsum()
    ax.plot(range(1, len(equity) + 1), equity.values, marker="o", label=label)


def write_plots(reports_dir: Path, *, trades: pd.DataFrame, trades_grey: pd.DataFrame,
                features: pd.DataFrame, sweep: dict[float, dict[str, float]]) -> dict[str, str]:
    """生成图表 PNG，返回 {key: filename}。无数据的图安全跳过。"""
    reports_dir = Path(reports_dir)
    charts: dict[str, str] = {}

    # 1) 权益曲线：baseline vs improved（按平仓顺序的累计 net PnL）
    fig, ax = plt.subplots(figsize=(7, 4))
    has_line = False
    if not trades.empty:
        for version in ("baseline_first_day_momentum_daily", "improved_grey_market_filter"):
            sub = trades[trades["strategy_version"] == version]
            if not sub.empty:
                _equity(ax, sub, version.replace("_", " "))
                has_line = True
    if has_line:
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_title("Cumulative net PnL (by exit order)")
        ax.set_xlabel("trade #")
        ax.set_ylabel("cumulative net PnL (HKD)")
        ax.legend()
        fig.tight_layout()
        path = reports_dir / "equity_curve.png"
        fig.savefig(path, dpi=110)
        charts["equity_curve"] = path.name
    plt.close(fig)

    # 2) 暗盘溢价 vs 个股前向收益散点（受控域内）
    if not trades_grey.empty and "grey_change_pct" in features.columns:
        merged = trades_grey.merge(
            features[["symbol", "grey_change_pct"]].drop_duplicates("symbol"), on="symbol", how="left"
        )
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.scatter(merged["grey_change_pct"], merged["return"])
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_title("Grey-market premium vs forward trade return")
        ax.set_xlabel("grey_change_pct")
        ax.set_ylabel("trade return")
        fig.tight_layout()
        path = reports_dir / "grey_vs_return.png"
        fig.savefig(path, dpi=110)
        charts["grey_vs_return"] = path.name
        plt.close(fig)

    # 3) 暗盘阈值扫描：total_return 随阈值变化
    if sweep:
        thresholds = sorted(sweep.keys())
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(thresholds, [sweep[t]["total_return"] for t in thresholds], marker="o")
        ax.set_title("Grey threshold sweep: total return (controlled universe)")
        ax.set_xlabel("grey_premium_min")
        ax.set_ylabel("total_return")
        fig.tight_layout()
        path = reports_dir / "grey_threshold_sweep.png"
        fig.savefig(path, dpi=110)
        charts["grey_threshold_sweep"] = path.name
        plt.close(fig)

    return charts
