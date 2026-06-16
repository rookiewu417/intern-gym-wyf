from __future__ import annotations

import json
import math
import statistics
from dataclasses import replace

import pandas as pd

from config import COST_SENSITIVITY_SCALES, DEFAULT, GREY_THRESHOLD_SWEEP, TRAILING_SWEEP
from costs import load_cost_model, scale_cost_model
from metrics import calculate_metrics, metrics_by_version
from paths import PROCESSED_DIR, RAW_DIR, REPORTS_DIR
from plots import write_plots
from report_tables import stratify_by_quantile, write_report_template
from stats import (
    bootstrap_total_return_ci,
    deflated_sharpe_ratio,
    holm_correction,
    permutation_selection_pvalue,
    reality_check_pvalue,
)
from strategy import baseline_mask, generate_trades, improved_mask, reversal_mask

VERSIONS = (
    ("baseline_first_day_momentum_daily", baseline_mask, {}),
    ("improved_grey_market_filter", improved_mask, {}),
    ("reversal_first_day_daily", reversal_mask, {}),
    # 增强版：improved 选股 + 追踪止损出场（让赢家跑），最大持仓放宽到 10 日
    ("improved_trailing_stop", improved_mask, {"trailing_stop_pct": 0.10, "holding_days": 10}),
)


def _json_safe(obj):
    """把 inf/nan 转 null，保证 metrics.json 是标准 JSON（jq / JS 可解析）。"""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def run_all_versions(features, daily, cost_model, config=DEFAULT) -> pd.DataFrame:
    frames = [generate_trades(features, daily, cost_model, version=v, mask=m, config=replace(config, **ov)) for v, m, ov in VERSIONS]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def cost_sensitivity(features, daily, cost_model, config=DEFAULT) -> dict[str, dict[float, dict[str, float]]]:
    """按版本做成本敏感性，避免把 baseline 与其子集 improved 合并造成重复计数。"""
    out: dict[str, dict[float, dict[str, float]]] = {}
    for version, mask, ov in VERSIONS:
        cfg_v = replace(config, **ov)
        out[version] = {
            scale: calculate_metrics(
                generate_trades(features, daily, scale_cost_model(cost_model, scale),
                                version=version, mask=mask, config=cfg_v)
            )
            for scale in COST_SENSITIVITY_SCALES
        }
    return out


def grey_threshold_sweep(features, daily, cost_model, config=DEFAULT) -> dict[float, dict[str, float]]:
    """受控实验：在『有暗盘数据』的信号域内扫描暗盘溢价门槛。

    improved_mask 永远只选中有暗盘数据的标的，因此改变门槛只在该子域内移动，
    把"暗盘溢价的区分力"与"数据可得性的选择效应"分离开。
    """
    out = {}
    for threshold in GREY_THRESHOLD_SWEEP:
        cfg = replace(config, grey_premium_min=threshold)
        trades = generate_trades(features, daily, cost_model, version="improved_grey_market_filter", mask=improved_mask, config=cfg)
        out[threshold] = calculate_metrics(trades)
    return out


def trailing_stop_sweep(features, daily, cost_model, config=DEFAULT) -> dict[float, dict[str, float]]:
    """追踪止损 trail% 扫描（improved 信号 + trailing 出场）：呈现收益随 trail 的单调性，不挑最优。"""
    out = {}
    for trail in TRAILING_SWEEP:
        cfg = replace(config, trailing_stop_pct=trail, holding_days=10)
        trades = generate_trades(features, daily, cost_model, version="improved_trailing_stop", mask=improved_mask, config=cfg)
        out[trail] = calculate_metrics(trades)
    return out


def grey_universe_trades(features, daily, cost_model, config=DEFAULT) -> pd.DataFrame:
    """baseline 交易，但限制在『有暗盘数据』的标的（门槛设 -inf）。"""
    cfg = replace(config, grey_premium_min=float("-inf"))
    return generate_trades(features, daily, cost_model, version="grey_universe", mask=improved_mask, config=cfg)


def grey_return_analysis(features: pd.DataFrame, trades_grey: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """暗盘可得域内：按暗盘溢价分位分层的收益 + 暗盘 vs 收益的 Spearman 相关。"""
    if trades_grey.empty or "grey_change_pct" not in features.columns:
        return pd.DataFrame(columns=["bucket", "count", "avg_return"]), float("nan")
    merged = trades_grey.merge(
        features[["symbol", "grey_change_pct"]].drop_duplicates("symbol"), on="symbol", how="left"
    )
    strat = stratify_by_quantile(merged, "grey_change_pct", bins=3)
    # Spearman = 秩的 Pearson 相关；用 rank() 避免引入 scipy 依赖
    corr = float(merged["grey_change_pct"].rank().corr(merged["return"].rank())) if len(merged) >= 2 else float("nan")
    return strat, corr


def tail_attribution(trades: pd.DataFrame, version: str = "improved_trailing_stop", top_n: int = 2) -> dict:
    """尾部集中度归因：top-N 贡献者 + 剔除后 total_return（序贯复利，与 metrics 口径同源）。

    让"收益集中于少数极热标的"从定性叙述变成可量化、可审计的证据。
    """
    sub = trades[trades["strategy_version"] == version] if "strategy_version" in trades.columns else trades
    if sub.empty:
        return {}
    ranked = sub.sort_values("return", ascending=False)
    top = [(str(s), float(r)) for s, r in zip(ranked["symbol"].head(top_n), ranked["return"].head(top_n))]
    rest = ranked["return"].iloc[top_n:].astype(float)
    full = float((1.0 + sub["return"].astype(float)).prod() - 1.0)
    ex_top = float((1.0 + rest).prod() - 1.0) if len(rest) else 0.0
    return {
        "version": version,
        "top_n": top_n,
        "top_contributors": top,
        "full_total_return": full,
        "ex_top_total_return": ex_top,
    }


def external_provenance(external_root) -> dict[str, int]:
    """从原始外部 CSV 统计【行覆盖】与【可靠性分级】，区别于 features 的【字段覆盖】。

    - IPO 行覆盖(含发行价/保荐人/行业/来源) vs 超购字段覆盖：避免用单一字段低估调研广度。
    - 暗盘数值可靠性：媒体明确收盘价 vs 近似值(取中值/区间/升幅描述)，标记后逐行可查。
    """
    from external_data import load_external  # 与 build_features 同一加载入口，保证口径一致

    ipo, grey = load_external(external_root)  # load_external 内部已 Path() 归一

    def _is_approx(note, grey_close) -> bool:
        s = str(note or "")
        # 近似标记：源文已注明取中值/近似/升幅区间，或仅有涨幅区间("-")、或收盘价未单列
        return any(k in s for k in ("取中值", "近似", "超五成", "区间", "-")) or pd.isna(grey_close)

    grey_present = int(grey["grey_change_pct"].notna().sum()) if not grey.empty else 0
    grey_approx = 0
    if not grey.empty:
        present = grey[grey["grey_change_pct"].notna()]
        grey_approx = int(sum(_is_approx(r.get("source_note"), r.get("grey_close")) for _, r in present.iterrows()))
    return {
        "external_ipo_rows_present": int(len(ipo)),
        "external_ipo_subscription_field_present": int(ipo["public_subscription_multiple"].notna().sum()) if not ipo.empty else 0,
        "external_grey_rows_present": int(len(grey)),
        "external_grey_value_present": grey_present,
        "external_grey_values_approximate": grey_approx,
        "external_grey_values_reported_exact": grey_present - grey_approx,
    }


def external_coverage_from_features(features: pd.DataFrame) -> dict[str, float]:
    total = int(len(features))

    def present(col: str) -> int:
        return int(features[col].notna().sum()) if col in features.columns else 0

    grey = present("grey_change_pct")
    ipo = present("public_subscription_multiple")
    # 信号标的口径：grey filter 只作用于 momentum 信号，故另报"信号标的覆盖率"，比 universe 分母更贴近策略
    sig = features[features["baseline_signal"].astype(bool)] if "baseline_signal" in features.columns else features.iloc[0:0]
    sig_total = int(len(sig))
    sig_grey = int(sig["grey_change_pct"].notna().sum()) if "grey_change_pct" in sig.columns and sig_total else 0
    return {
        "external_symbols_total": total,
        "external_grey_change_pct_present": grey,
        "external_grey_coverage_ratio": round(grey / total, 4) if total else 0.0,
        "external_ipo_subscription_present": ipo,
        "external_ipo_coverage_ratio": round(ipo / total, 4) if total else 0.0,
        "external_signal_symbols_total": sig_total,
        "external_grey_present_on_signals": sig_grey,
        "external_grey_coverage_on_signals": round(sig_grey / sig_total, 4) if sig_total else 0.0,
    }


def data_snooping_diagnostics(features, daily, cost_model, base_returns, config=DEFAULT) -> dict:
    """对 grey sweep 候选集做 data-snooping 校正：reality-check p、Holm 最小校正 p、Deflated Sharpe。

    候选 = 各暗盘门槛档（都从 baseline 动量信号池里挑子集，可比）；池 = baseline 池逐笔收益。
    回答"在多个门槛里挑出的最佳表现，能否被'随机选同样笔数'解释（且已惩罚多重比较）"。
    """
    base = list(base_returns)
    if not base:
        return {}
    cands = []  # (label, k, total_return, returns, sharpe)
    for t in GREY_THRESHOLD_SWEEP:
        cfg = replace(config, grey_premium_min=t)
        tr = generate_trades(features, daily, cost_model, version="improved_grey_market_filter", mask=improved_mask, config=cfg)
        rets = [float(x) for x in tr["return"].tolist()] if not tr.empty else []
        if not rets:
            continue
        total = math.prod(1.0 + x for x in rets) - 1.0
        sd = statistics.stdev(rets) if len(rets) >= 2 else 0.0
        sharpe = statistics.fmean(rets) / sd if sd > 0 else float("nan")
        cands.append((f"grey>={t:g}", len(rets), total, rets, sharpe))
    if not cands:
        return {}
    ks = [k for _, k, _, _, _ in cands]
    observed_best = max(total for _, _, total, _, _ in cands)
    per_p = {lab: permutation_selection_pvalue(base, k, total) for lab, k, total, _, _ in cands}
    holm = holm_correction(per_p)
    sharpes = [s for *_, s in cands if s == s]  # 去 NaN
    sharpe_var = statistics.variance(sharpes) if len(sharpes) >= 2 else 0.0
    n_trials = len(VERSIONS) + len(GREY_THRESHOLD_SWEEP) + len(TRAILING_SWEEP)  # 保守下界：不含历史已移除的 multifactor
    imp = next((rets for lab, _, _, rets, _ in cands if lab == "grey>=0"), [])
    dsr = deflated_sharpe_ratio(imp, n_trials, sharpe_var) if imp else None
    return {
        "reality_check_pvalue": reality_check_pvalue(base, ks, observed_best),
        "holm_min_adjusted_pvalue": min(holm.values()) if holm else float("nan"),
        "holm_adjusted_pvalues": holm,
        "deflated_sharpe_ratio": dsr,
        "n_trials": n_trials,
        "observed_best_total_return": observed_best,
        "dsr_strategy": "improved_grey_market_filter@grey>=0",
        "dsr_n_obs": len(imp),
    }


def main() -> int:
    features = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    daily = pd.read_parquet(RAW_DIR / "daily_bars.parquet")
    cost_model = load_cost_model(RAW_DIR / "cost_model.json")
    coverage = {}
    cov_path = RAW_DIR / "coverage_summary.json"
    if cov_path.exists():
        coverage = json.loads(cov_path.read_text(encoding="utf-8"))
    ext_cov = external_coverage_from_features(features)
    coverage.update(ext_cov)
    provenance = external_provenance(RAW_DIR.parent / "external")
    coverage.update(provenance)

    trades = run_all_versions(features, daily, cost_model)
    tail_attr = tail_attribution(trades)
    by_version = metrics_by_version(trades)
    sensitivity = cost_sensitivity(features, daily, cost_model)
    sweep = grey_threshold_sweep(features, daily, cost_model)
    trailing_sweep = trailing_stop_sweep(features, daily, cost_model)

    trades_grey = grey_universe_trades(features, daily, cost_model)
    grey_strat, grey_corr = grey_return_analysis(features, trades_grey)

    # IPO 分层基于 baseline 全集（去重），避免 improved 子集重复同一标的
    sub_strat = pd.DataFrame()
    base_trades = trades[trades["strategy_version"] == "baseline_first_day_momentum_daily"] if not trades.empty else trades
    if not base_trades.empty and "public_subscription_multiple" in features.columns:
        merged = base_trades.merge(features[["symbol", "public_subscription_multiple"]].drop_duplicates("symbol"), on="symbol", how="left")
        sub_strat = stratify_by_quantile(merged, "public_subscription_multiple", bins=3)

    # 过拟合量化：每版本 total_return 的 bootstrap 95% CI；子集选择策略 vs 随机选股的置换 p
    base_returns = base_trades["return"].tolist() if not base_trades.empty else []
    total_return_ci = {
        v: list(bootstrap_total_return_ci(trades[trades["strategy_version"] == v]["return"]))
        for v in by_version
    }
    selection_pvalue = {
        v: permutation_selection_pvalue(base_returns, int(by_version[v]["trade_count"]), float(by_version[v]["total_return"]))
        for v in ("improved_grey_market_filter",)
        if v in by_version and base_returns
    }
    data_snooping = data_snooping_diagnostics(features, daily, cost_model, base_returns)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    charts = write_plots(REPORTS_DIR, trades=trades, trades_grey=trades_grey, features=features, sweep=sweep)
    trades.to_csv(REPORTS_DIR / "trades.csv", index=False)
    metrics_payload = {
        "by_version": by_version,
        "cost_sensitivity": {ver: {str(k): v for k, v in scales.items()} for ver, scales in sensitivity.items()},
        "grey_threshold_sweep": {str(k): v for k, v in sweep.items()},
        "trailing_stop_sweep": {str(k): v for k, v in trailing_sweep.items()},
        "grey_return_spearman": grey_corr,
        "total_return_ci": total_return_ci,
        "selection_pvalue": selection_pvalue,
        "data_snooping": data_snooping,
        "external_coverage": ext_cov,
        "external_provenance": provenance,
        "tail_attribution": tail_attr,
    }
    (REPORTS_DIR / "metrics.json").write_text(
        json.dumps(_json_safe(metrics_payload), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    write_report_template(
        REPORTS_DIR / "research_report.md",
        by_version=by_version, sensitivity=sensitivity, coverage=coverage, cost_model=cost_model,
        sub_stratification=sub_strat, grey_stratification=grey_strat, grey_corr=grey_corr,
        grey_sweep=sweep, trailing_sweep=trailing_sweep,
        total_return_ci=total_return_ci, selection_pvalue=selection_pvalue, data_snooping=data_snooping,
        tail_attribution=tail_attr, charts=charts,
    )
    print(json.dumps(_json_safe(metrics_payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
