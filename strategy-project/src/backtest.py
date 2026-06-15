from __future__ import annotations

import json
from dataclasses import replace

import pandas as pd

from config import COST_SENSITIVITY_SCALES, DEFAULT, GREY_THRESHOLD_SWEEP
from costs import load_cost_model, scale_cost_model
from metrics import calculate_metrics, metrics_by_version
from paths import PROCESSED_DIR, RAW_DIR, REPORTS_DIR
from plots import write_plots
from report_tables import stratify_by_quantile, write_report_template
from strategy import baseline_mask, generate_trades, improved_mask

VERSIONS = (
    ("baseline_first_day_momentum_daily", baseline_mask),
    ("improved_grey_market_filter", improved_mask),
)


def run_all_versions(features, daily, cost_model, config=DEFAULT) -> pd.DataFrame:
    frames = [generate_trades(features, daily, cost_model, version=v, mask=m, config=config) for v, m in VERSIONS]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def cost_sensitivity(features, daily, cost_model, config=DEFAULT) -> dict[float, dict[str, float]]:
    out = {}
    for scale in COST_SENSITIVITY_SCALES:
        trades = run_all_versions(features, daily, scale_cost_model(cost_model, scale), config)
        out[scale] = calculate_metrics(trades)
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


def external_coverage_from_features(features: pd.DataFrame) -> dict[str, float]:
    total = int(len(features))

    def present(col: str) -> int:
        return int(features[col].notna().sum()) if col in features.columns else 0

    grey = present("grey_change_pct")
    ipo = present("public_subscription_multiple")
    return {
        "external_symbols_total": total,
        "external_grey_change_pct_present": grey,
        "external_grey_coverage_ratio": round(grey / total, 4) if total else 0.0,
        "external_ipo_subscription_present": ipo,
        "external_ipo_coverage_ratio": round(ipo / total, 4) if total else 0.0,
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

    trades = run_all_versions(features, daily, cost_model)
    by_version = metrics_by_version(trades)
    overall = calculate_metrics(trades)
    sensitivity = cost_sensitivity(features, daily, cost_model)
    sweep = grey_threshold_sweep(features, daily, cost_model)

    trades_grey = grey_universe_trades(features, daily, cost_model)
    grey_strat, grey_corr = grey_return_analysis(features, trades_grey)

    sub_strat = pd.DataFrame()
    if not trades.empty and "public_subscription_multiple" in features.columns:
        merged = trades.merge(features[["symbol", "public_subscription_multiple"]].drop_duplicates("symbol"), on="symbol", how="left")
        sub_strat = stratify_by_quantile(merged, "public_subscription_multiple", bins=3)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    charts = write_plots(REPORTS_DIR, trades=trades, trades_grey=trades_grey, features=features, sweep=sweep)
    trades.to_csv(REPORTS_DIR / "trades.csv", index=False)
    metrics_payload = {
        "overall": overall,
        "by_version": by_version,
        "cost_sensitivity": {str(k): v for k, v in sensitivity.items()},
        "grey_threshold_sweep": {str(k): v for k, v in sweep.items()},
        "grey_return_spearman": grey_corr,
        "external_coverage": ext_cov,
    }
    (REPORTS_DIR / "metrics.json").write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report_template(
        overall, REPORTS_DIR / "research_report.md",
        by_version=by_version, sensitivity=sensitivity, coverage=coverage,
        sub_stratification=sub_strat, grey_stratification=grey_strat, grey_corr=grey_corr,
        grey_sweep=sweep, charts=charts,
    )
    print(json.dumps(metrics_payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
