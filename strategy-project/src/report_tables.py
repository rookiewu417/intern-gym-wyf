from __future__ import annotations

from pathlib import Path

import pandas as pd

_COMPARE_KEYS = ["trade_count", "win_rate", "total_return", "max_drawdown", "average_holding_days", "profit_factor"]


def comparison_table(by_version: dict[str, dict[str, float]]) -> str:
    df = pd.DataFrame(by_version).T
    cols = [c for c in _COMPARE_KEYS if c in df.columns]
    return df[cols].reset_index(names="strategy_version").to_markdown(index=False)


def sensitivity_table(rows: dict[float, dict[str, float]]) -> str:
    import tabulate as _tab
    df = pd.DataFrame(rows).T
    df.index = df.index.map(lambda x: f"{x:.1f}")
    reset = df.reset_index(names="cost_scale")
    return _tab.tabulate(reset.values.tolist(), headers=list(reset.columns), tablefmt="pipe", disable_numparse=True)


def stratify_by_quantile(trades: pd.DataFrame, column: str, *, bins: int = 3) -> pd.DataFrame:
    work = trades.dropna(subset=[column]).copy()
    if work.empty:
        return pd.DataFrame(columns=["bucket", "count", "avg_return"])
    work["bucket"] = pd.qcut(work[column], q=min(bins, work[column].nunique()), duplicates="drop")
    grouped = work.groupby("bucket", observed=True)["return"].agg(count="count", avg_return="mean")
    return grouped.reset_index()


def write_report_template(
    metrics: dict[str, float],
    path: Path,
    *,
    by_version: dict[str, dict[str, float]] | None = None,
    sensitivity: dict[float, dict[str, float]] | None = None,
    coverage: dict | None = None,
    stratification_md: str = "",
) -> None:
    compare_md = comparison_table(by_version) if by_version else "(无对照数据)"
    sens_md = sensitivity_table(sensitivity) if sensitivity else "(无敏感性数据)"
    cov_md = "\n".join(f"- {k}: {v}" for k, v in (coverage or {}).items()) or "(无 coverage)"
    content = f"""# IPO / New Listing Daily Strategy Research

## Executive Summary

- 总 trade_count: {metrics.get("trade_count", 0)}
- win_rate: {metrics.get("win_rate", 0.0):.4f}
- total_return: {metrics.get("total_return", 0.0):.4f}
- max_drawdown: {metrics.get("max_drawdown", 0.0):.2f}

## Data

API 下载覆盖、缺失/停牌/无成交，及自行调研的 IPO/暗盘来源与可靠性：

{cov_md}

## Strategy Definition

- Baseline：首日动量（day1 close/open-1 > 阈值，day2 open 入场，持 K 日，止损/止盈，扣费）。
- Improved：在 baseline 上叠加暗盘溢价主过滤（grey_change_pct >= 阈值），缺暗盘数据者不入场。
- 无未来函数：信号仅用 day1 与上市前/上市时点的外部数据；执行价 day2 open。
- 成本：买/卖 bps + 滑点 + 最低费，按成交额计。

## Results

### Baseline vs Improved

{compare_md}

### Cost Sensitivity（全策略 total_return 等）

{sens_md}

### IPO 特征分层（按超购倍数）

{stratification_md or "(无分层数据)"}

## Analysis

（解释收益/亏损来源、改进是否稳健、暗盘过滤的作用与样本量限制。）

## Next Steps

（按上市月滚动阈值、多因子组合、扩大样本、更真实的执行建模。）
"""
    path.write_text(content, encoding="utf-8")
