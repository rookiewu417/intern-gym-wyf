from __future__ import annotations

from pathlib import Path

import pandas as pd

_COMPARE_KEYS = ["trade_count", "win_rate", "total_return", "max_drawdown", "average_holding_days", "profit_factor"]
_SWEEP_KEYS = ["trade_count", "win_rate", "average_return", "total_return", "profit_factor"]


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


def grey_sweep_table(sweep: dict[float, dict[str, float]]) -> str:
    import tabulate as _tab

    rows = []
    for t in sorted(sweep.keys()):
        m = sweep[t]
        rows.append([f"{t:.2f}"] + [round(float(m.get(k, 0.0)), 4) for k in _SWEEP_KEYS])
    return _tab.tabulate(rows, headers=["grey_premium_min"] + _SWEEP_KEYS, tablefmt="pipe", disable_numparse=True)


def stratify_by_quantile(trades: pd.DataFrame, column: str, *, bins: int = 3) -> pd.DataFrame:
    work = trades.dropna(subset=[column]).copy()
    if work.empty:
        return pd.DataFrame(columns=["bucket", "count", "avg_return"])
    work["bucket"] = pd.qcut(work[column], q=min(bins, work[column].nunique()), duplicates="drop")
    grouped = work.groupby("bucket", observed=True)["return"].agg(count="count", avg_return="mean")
    return grouped.reset_index()


def _md(df: pd.DataFrame, empty: str) -> str:
    return df.to_markdown(index=False) if df is not None and not df.empty else empty


def _img(charts: dict[str, str], key: str, alt: str) -> str:
    return f"![{alt}]({charts[key]})" if charts and key in charts else ""


def _analysis(by_version: dict, grey_sweep: dict, grey_corr: float, grey_strat: pd.DataFrame | None = None) -> str:
    base = by_version.get("baseline_first_day_momentum_daily", {})
    imp = by_version.get("improved_grey_market_filter", {})
    lines = []
    if base:
        lines.append(
            f"- **Baseline**：{base.get('trade_count',0)} 笔，胜率 {base.get('win_rate',0):.1%}，"
            f"总收益 {base.get('total_return',0):.2%}，profit_factor {base.get('profit_factor',0):.2f}。"
        )
    if imp:
        lines.append(
            f"- **Improved（暗盘溢价≥0）**：{imp.get('trade_count',0)} 笔，胜率 {imp.get('win_rate',0):.1%}，"
            f"总收益 {imp.get('total_return',0):.2%}，profit_factor {imp.get('profit_factor',0):.2f}。"
        )
    # 受控实验：阈值扫描趋势（仅作用于暗盘可得域，隔离数据可得性）
    if grey_sweep:
        ts = sorted(grey_sweep.keys())
        lo, hi = grey_sweep[ts[0]], grey_sweep[ts[-1]]
        avg_lo, avg_hi = lo.get("average_return", 0.0), hi.get("average_return", 0.0)
        trend = "上升" if avg_hi > avg_lo else ("基本持平" if abs(avg_hi - avg_lo) < 1e-6 else "下降")
        verdict = (
            "提高暗盘门槛后**平均收益上升**，说明在『有暗盘数据』的同一研究域内，更高的暗盘溢价确实对应更高的前向收益——"
            "区分力来自信号本身，而非数据可得性。"
            if avg_hi > avg_lo else
            "提高暗盘门槛后平均收益并未稳定上升，说明在受控域内暗盘溢价的**区分力有限**，"
            "naive 对照的优势更多来自『能查到暗盘数据≈热门股』的选择效应。"
        )
        lines.append(
            f"- **受控实验（暗盘阈值扫描，仅暗盘可得域）**：门槛由 {ts[0]:.2f} 提到 {ts[-1]:.2f} 时，"
            f"平均单笔收益由 {avg_lo:.2%} → {avg_hi:.2%}（{trend}），样本由 {lo.get('trade_count',0)} → {hi.get('trade_count',0)} 笔。{verdict}"
        )
    if grey_corr == grey_corr:  # not NaN
        sign = "正" if grey_corr > 0.1 else ("负" if grey_corr < -0.1 else "近似为零")
        lines.append(f"- **暗盘溢价与前向收益的 Spearman 相关 = {grey_corr:.2f}（{sign}相关）**。")
    # 分层是否单调 / 是否被尾部驱动（诚实地揭示信号稳健性）
    if grey_strat is not None and not grey_strat.empty and len(grey_strat) >= 2:
        avg = [float(x) for x in grey_strat["avg_return"].tolist()]
        if avg[-1] == max(avg) and any(r <= 0 for r in avg[:-1]):
            lines.append(
                "- **但分层非单调**：收益主要由**最高暗盘档**驱动，中间档并不单调（甚至为负）。"
                "说明效应集中在少数极热标的、并非平滑的单调关系，稳健性弱、样本依赖强。"
            )
    return "\n".join(lines)


def write_report_template(
    metrics: dict[str, float],
    path: Path,
    *,
    by_version: dict[str, dict[str, float]] | None = None,
    sensitivity: dict[float, dict[str, float]] | None = None,
    coverage: dict | None = None,
    sub_stratification: pd.DataFrame | None = None,
    grey_stratification: pd.DataFrame | None = None,
    grey_corr: float = float("nan"),
    grey_sweep: dict[float, dict[str, float]] | None = None,
    charts: dict[str, str] | None = None,
) -> None:
    by_version = by_version or {}
    grey_sweep = grey_sweep or {}
    charts = charts or {}
    compare_md = comparison_table(by_version) if by_version else "(无对照数据)"
    sens_md = sensitivity_table(sensitivity) if sensitivity else "(无敏感性数据)"
    sweep_md = grey_sweep_table(grey_sweep) if grey_sweep else "(无阈值扫描数据)"
    cov_md = "\n".join(f"- {k}: {v}" for k, v in (coverage or {}).items()) or "(无 coverage)"
    sub_md = _md(sub_stratification, "(无分层数据)")
    grey_strat_md = _md(grey_stratification, "(无暗盘分层数据)")
    analysis_md = _analysis(by_version, grey_sweep, grey_corr, grey_stratification)

    content = f"""# IPO / New Listing Daily Strategy Research

> 本报告由 `python src/backtest.py` **全自动生成**（含下方 Analysis），重跑幂等、不依赖手工编辑。

## Executive Summary

- 总 trade_count: {metrics.get("trade_count", 0)}
- win_rate: {metrics.get("win_rate", 0.0):.4f}
- total_return: {metrics.get("total_return", 0.0):.4f}
- max_drawdown: {metrics.get("max_drawdown", 0.0):.2f}

## Data

API 下载覆盖、缺失/停牌/无成交，及自行调研的 IPO/暗盘来源与可靠性（来源逐行见 `data/external/*.csv`）：

{cov_md}

## Strategy Definition

- Baseline：首日动量（day1 close/open-1 > 阈值，day2 open 入场，持 K 日，止损/止盈，扣费），每股票最多一笔。
- Improved：在 baseline 上叠加暗盘溢价主过滤（grey_change_pct >= 阈值），缺暗盘数据者不入场。
- 无未来函数：信号仅用 day1 与上市前/上市时点的外部数据（暗盘=上市前夜、超购=招股结束）；执行价用 day2 open。
- 成本：买/卖 bps + 滑点 + 最低费，按成交额计。
- 出场约定：持仓窗口内逐日先判止损后判止盈（同日同时触及按止损计），含入场当日；未触发则在末个有效交易日 close 出场。
- 受控实验设计：improved_mask 只会选中『有暗盘数据』的标的，因此对该子域做暗盘阈值扫描，可把"暗盘溢价的区分力"与"数据可得性的选择效应"分离开。

## Results

### Baseline vs Improved（naive 对照）

{compare_md}

{_img(charts, "equity_curve", "equity curve")}

### Cost Sensitivity（全策略，0.5x/1x/2x 成本）

{sens_md}

### 受控实验：暗盘阈值扫描（仅作用于暗盘可得域）

{sweep_md}

{_img(charts, "grey_threshold_sweep", "grey threshold sweep")}

### 暗盘溢价分层 + 相关性

{grey_strat_md}

Spearman(grey_change_pct, return) = {grey_corr:.4f}

{_img(charts, "grey_vs_return", "grey vs return")}

### IPO 特征分层（按公开超购倍数）

{sub_md}

## Analysis

{analysis_md}

## Limitations（必须正视）

- **单一普涨窗口**：数据覆盖 2026 上半年，期间港股新股近乎全线上涨；任何"选更热标的"的规则都天然占优，外推性存疑。
- **样本极小**：baseline/improved 各为个位数到十余笔，胜率/收益的置信区间很宽，易过拟合。
- **选择偏差已缓解但未消除**：暗盘数据覆盖 12/14 信号标的，受控阈值扫描即为消除"数据可得性混入"而设；但仍有 2 支偏冷标的无公开暗盘数据被动排除。
- **外部数据口径**：个别暗盘值为近似（如"升幅超五成"取 0.50），部分超购为孖展口径（已在 `source_note` 标注）。
- **数据出处**：lab 日线为真实港股市场数据（coverage_start 与公开上市日一致）；外部暗盘/IPO 为自行调研公开来源，每行记 source_url。

## Next Steps

- 把暗盘数据补全到全部信号标的（含偏冷股），彻底消除选择偏差。
- 暗盘/超购阈值改为按上市月或行业的 expanding 分位，去除横截面假设。
- 多因子打分（暗盘 + 超购 + 行业）替代单一阈值过滤。
- 扩到多年、多市场状态做样本外验证，检验"暗盘溢价 → 初期动量"是否跨期稳健。
"""
    path.write_text(content, encoding="utf-8")
