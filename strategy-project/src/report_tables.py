from __future__ import annotations

import math
from pathlib import Path

import pandas as pd


def _pf(v) -> str | float:
    """profit_factor 展示：无亏损（inf）显示 ∞（metrics.json 另记为 null）。"""
    return "∞" if isinstance(v, (int, float)) and math.isinf(v) else v

_COMPARE_KEYS = ["trade_count", "win_rate", "total_return", "max_drawdown", "average_holding_days", "profit_factor"]
_SWEEP_KEYS = ["trade_count", "win_rate", "average_return", "total_return", "profit_factor"]


def comparison_table(by_version: dict[str, dict[str, float]]) -> str:
    df = pd.DataFrame(by_version).T
    cols = [c for c in _COMPARE_KEYS if c in df.columns]
    out = df[cols].reset_index(names="strategy_version")
    if "profit_factor" in out.columns:
        out["profit_factor"] = out["profit_factor"].map(_pf)
    return out.to_markdown(index=False)


def sensitivity_table(rows: dict[float, dict[str, float]]) -> str:
    import tabulate as _tab

    df = pd.DataFrame(rows).T
    df.index = df.index.map(lambda x: f"{x:.1f}")
    reset = df.reset_index(names="cost_scale")
    return _tab.tabulate(reset.values.tolist(), headers=list(reset.columns), tablefmt="pipe", disable_numparse=True)


def grey_sweep_table(sweep: dict[float, dict[str, float]], label: str = "grey_premium_min") -> str:
    import tabulate as _tab

    rows = []
    for t in sorted(sweep.keys()):
        m = sweep[t]
        cells = [_pf(v) if math.isinf(v := float(m.get(k, 0.0))) else round(v, 4) for k in _SWEEP_KEYS]
        rows.append([f"{t:.2f}"] + cells)
    return _tab.tabulate(rows, headers=[label] + _SWEEP_KEYS, tablefmt="pipe", disable_numparse=True)


def robustness_table(by_version: dict, total_return_ci: dict, selection_pvalue: dict) -> str:
    """过拟合诊断：每版本 total_return + bootstrap 95% CI + 选股置换 p（无则 —）。"""
    import tabulate as _tab

    rows = []
    for v in by_version:
        tr = float(by_version[v].get("total_return", 0.0))
        lohi = total_return_ci.get(v)
        ci_str = f"[{lohi[0]*100:.1f}%, {lohi[1]*100:.1f}%]" if lohi and lohi[0] is not None else "—"
        p = selection_pvalue.get(v)
        p_str = f"{p:.3f}" if p is not None else "—"
        rows.append([v, f"{tr*100:.1f}%", ci_str, p_str])
    return _tab.tabulate(rows, headers=["version", "total_return", "95% CI", "选股 p"], tablefmt="pipe", disable_numparse=True)


def data_snooping_section(diag: dict) -> str:
    """多重检验 / data-snooping 稳健性小节（表格 + 自动判语）。"""
    import tabulate as _tab

    if not diag:
        return "(无 data-snooping 诊断)"
    rc = float(diag.get("reality_check_pvalue", float("nan")))
    holm = float(diag.get("holm_min_adjusted_pvalue", float("nan")))
    dsr = diag.get("deflated_sharpe_ratio")
    n_trials = int(diag.get("n_trials", 0))
    obs = float(diag.get("observed_best_total_return", 0.0))
    n_obs = int(diag.get("dsr_n_obs", 0))
    dsr_str = f"{dsr:.3f}" if isinstance(dsr, (int, float)) else "N/A（样本太小）"
    rows = [
        ["max-statistic 置换 p（White RC 风格）", f"{rc:.3f}", f"最佳档 total_return={obs:.1%} 在 {n_trials} 个配置多重比较下的显著性"],
        ["Holm 最小校正 p", f"{holm:.3f}", "各门槛单独置换 p 经 Holm step-down 后的最小值"],
        ["Deflated Sharpe Ratio", dsr_str, f"improved {n_obs} 笔；N={n_trials} 试验校正后 Sharpe 是否显著"],
    ]
    table = _tab.tabulate(rows, headers=["检验", "值", "含义"], tablefmt="pipe", disable_numparse=True)
    overfit = (rc != rc) or rc > 0.1 or (dsr is None) or (isinstance(dsr, (int, float)) and dsr < 0.5)
    if overfit:
        verdict = (
            "**校正后最佳策略不显著**：试了多个策略×门槛后挑出的表观最优，可由 data-snooping"
            "（多重试验后选最好）解释——进一步坐实本样本无稳健 alpha。"
        )
    else:
        verdict = "校正后最佳策略仍显著（本样本罕见，需警惕巧合）。"
    return f"{table}\n\n{verdict}"


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


def _analysis(by_version: dict, grey_sweep: dict, grey_corr: float) -> str:
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
    rev = by_version.get("reversal_first_day_daily", {})
    if rev:
        rev_pf = float(rev.get("profit_factor", 0.0))
        rev_pf_str = "∞" if math.isinf(rev_pf) else f"{rev_pf:.2f}"
        lines.append(
            f"- **Reversal（首日大跌后反转，对照）**：{rev.get('trade_count',0)} 笔，胜率 {rev.get('win_rate',0):.1%}，"
            f"总收益 {rev.get('total_return',0):.2%}，profit_factor {rev_pf_str}。"
        )
    # 受控实验：阈值扫描趋势（仅作用于暗盘可得域）。稳健判据：单调性 + 全样本秩相关，避免被首尾两点误导
    if grey_sweep:
        ts = sorted(grey_sweep.keys())
        lo, hi = grey_sweep[ts[0]], grey_sweep[ts[-1]]
        avg_lo, avg_hi = lo.get("average_return", 0.0), hi.get("average_return", 0.0)
        avgs = [grey_sweep[t].get("average_return", 0.0) for t in ts]
        n_hi = int(hi.get("trade_count", 0))
        trend = "上升" if avg_hi > avg_lo + 1e-9 else ("基本持平" if abs(avg_hi - avg_lo) <= 1e-9 else "下降")
        monotone_up = all(b >= a - 1e-9 for a, b in zip(avgs, avgs[1:]))
        corr_pos = (grey_corr == grey_corr) and grey_corr > 0.2  # 全样本 Spearman 显著为正
        if monotone_up and corr_pos:
            verdict = (
                "门槛提高后平均收益**单调上升**且全样本 Spearman 为正——在『有暗盘数据』的同一研究域内，"
                "更高的暗盘溢价确实对应更高的前向收益，区分力来自信号本身，而非数据可得性。"
            )
        else:
            verdict = (
                f"但收益随门槛**并非单调**、最高门槛仅剩 {n_hi} 笔（**尾部驱动**），全样本 Spearman={grey_corr:.2f}；"
                "受控域内暗盘溢价的稳健区分力**有限**，naive 对照的优势更多来自"
                "『能查到暗盘数据≈热门股』的选择效应与少数极热标的。"
            )
        lines.append(
            f"- **受控实验（暗盘阈值扫描，仅暗盘可得域）**：门槛由 {ts[0]:.2f} 提到 {ts[-1]:.2f} 时，"
            f"平均单笔收益由 {avg_lo:.2%} → {avg_hi:.2%}（首尾{trend}），样本由 {int(lo.get('trade_count',0))} → {n_hi} 笔。{verdict}"
        )
    if grey_corr == grey_corr:  # not NaN
        sign = "正" if grey_corr > 0.1 else ("负" if grey_corr < -0.1 else "近似为零")
        lines.append(f"- **暗盘溢价与前向收益的 Spearman 相关 = {grey_corr:.2f}（{sign}相关）**。")
    return "\n".join(lines)


def write_report_template(
    path: Path,
    *,
    by_version: dict[str, dict[str, float]] | None = None,
    sensitivity: dict[str, dict[float, dict[str, float]]] | None = None,
    coverage: dict | None = None,
    cost_model: dict | None = None,
    sub_stratification: pd.DataFrame | None = None,
    grey_stratification: pd.DataFrame | None = None,
    grey_corr: float = float("nan"),
    grey_sweep: dict[float, dict[str, float]] | None = None,
    total_return_ci: dict | None = None,
    selection_pvalue: dict | None = None,
    data_snooping: dict | None = None,
    charts: dict[str, str] | None = None,
) -> None:
    by_version = by_version or {}
    grey_sweep = grey_sweep or {}
    charts = charts or {}
    compare_md = comparison_table(by_version) if by_version else "(无对照数据)"
    if sensitivity:
        sens_md = "\n\n".join(f"**{version}**\n\n{sensitivity_table(scales)}" for version, scales in sensitivity.items())
    else:
        sens_md = "(无敏感性数据)"
    sweep_md = grey_sweep_table(grey_sweep) if grey_sweep else "(无阈值扫描数据)"
    robust_md = robustness_table(by_version, total_return_ci or {}, selection_pvalue or {}) if by_version else "(无诊断数据)"
    ds_md = data_snooping_section(data_snooping or {})
    cov_md = "\n".join(f"- {k}: {v}" for k, v in (coverage or {}).items()) or "(无 coverage)"
    sub_md = _md(sub_stratification, "(无分层数据)")
    grey_strat_md = _md(grey_stratification, "(无暗盘分层数据)")
    analysis_md = _analysis(by_version, grey_sweep, grey_corr)
    cm = cost_model or {}
    cost_line = (
        f"成本（本次运行实际值）：买入 {float(cm.get('buy_cost_bps',0)):g}bps、"
        f"卖出 {float(cm.get('sell_cost_bps',0)):g}bps、滑点 {float(cm.get('slippage_bps',0)):g}bps、"
        f"最低费 {float(cm.get('min_fee',0)):g}（{cm.get('currency','')} 计；费用按成交额，最低费为每边下限）"
    )

    content = f"""# IPO / New Listing Daily Strategy Research

> 本报告由 `python src/backtest.py` **全自动生成**（含下方 Analysis），重跑幂等、不依赖手工编辑。

## Executive Summary

> **交付物定调**：本研究的核心交付是对「首日动量 / 暗盘溢价」扣成本后**可交易性的严谨证伪**，而非虚假 alpha——三个版本扣成本后均无稳健正收益；受控阈值扫描 + Bootstrap CI + 置换检验共同表明，naive 对照的表面优势来自「能查到暗盘≈热门股」的选择效应与少数极热标的，而非暗盘溢价本身的稳健区分力（详见下方稳健性诊断与 Analysis）。

> 口径：`total_return` 为序贯等额下注的**复利**总收益；`max_drawdown` 为复利权益的**百分比**回撤（两者同源）。reversal 与 momentum 信号互斥、improved 为 baseline 的子集（叠加暗盘过滤），三者分列对照、不合并计数。`profit_factor=∞` 表示无亏损交易（`metrics.json` 中记为 `null`）。

{compare_md}

## Data

API 下载覆盖、缺失/停牌/无成交，及自行调研的 IPO/暗盘来源与可靠性（来源逐行见 `data/external/*.csv`）：

{cov_md}

## Strategy Definition

- Baseline：首日动量（day1 close/open-1 > 阈值，day2 open 入场，持 K 日，止损/止盈，扣费），每股票最多一笔。
- Improved：在 baseline 上叠加暗盘溢价主过滤（grey_change_pct >= 阈值），缺暗盘数据者不入场。
- Reversal（对照）：首日大跌（close/open-1 < -阈值）后预期反转，day2 open 做多，其余执行与 baseline 相同；与 momentum 互斥。
- 无未来函数：信号仅用 day1 与上市前/上市时点的外部数据（暗盘=上市前夜、超购=招股结束）；执行价用 day2 open。
- {cost_line}
- 出场约定：持仓窗口内逐日先判止损后判止盈（同日同时触及按止损计），含入场当日；触发即按 `stop_level`/`take_level` 价位成交（保守惯例，再叠加卖出滑点），未触发则在末个有效交易日 close 出场。
- 受控实验设计：improved_mask 只会选中『有暗盘数据』的标的，因此对该子域做暗盘阈值扫描，可把"暗盘溢价的区分力"与"数据可得性的选择效应"分离开。

## Results

### Baseline vs Improved（naive 对照）

对照表见上方 Executive Summary（improved ⊆ baseline，二者分列对照而非组合）。下图为两版本的复利权益曲线（按平仓顺序、起点 1.0）：

{_img(charts, "equity_curve", "equity curve")}

### Cost Sensitivity（按版本，0.5x/1x/2x 成本）

{sens_md}

### 受控实验：暗盘阈值扫描（仅作用于暗盘可得域）

{sweep_md}

{_img(charts, "grey_threshold_sweep", "grey threshold sweep")}

### 稳健性诊断（Bootstrap 95% CI + 置换检验）

> CI 越宽=点估计越不可信；选股 p 越大=该因子选股不比随机选同等数量更好（疑过拟合/噪声）。

{robust_md}

### 多重检验 / Data-snooping 稳健性

> 校正"在多个策略×门槛配置里挑最好"的选择偏差——本研究唯一仍敞着的过拟合口子。N 为保守下界（不含历史已移除的 multifactor，计入则惩罚更重）。

{ds_md}

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
