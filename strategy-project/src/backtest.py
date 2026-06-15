from __future__ import annotations

import json

import pandas as pd

from config import COST_SENSITIVITY_SCALES, DEFAULT
from costs import load_cost_model, scale_cost_model
from metrics import calculate_metrics, metrics_by_version
from paths import PROCESSED_DIR, RAW_DIR, REPORTS_DIR
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


def main() -> int:
    features = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    daily = pd.read_parquet(RAW_DIR / "daily_bars.parquet")
    cost_model = load_cost_model(RAW_DIR / "cost_model.json")
    coverage = {}
    cov_path = RAW_DIR / "coverage_summary.json"
    if cov_path.exists():
        coverage = json.loads(cov_path.read_text(encoding="utf-8"))

    trades = run_all_versions(features, daily, cost_model)
    by_version = metrics_by_version(trades)
    overall = calculate_metrics(trades)
    sensitivity = cost_sensitivity(features, daily, cost_model)

    strat_md = ""
    if not trades.empty and "public_subscription_multiple" in features.columns:
        merged = trades.merge(features[["symbol", "public_subscription_multiple"]].drop_duplicates("symbol"), on="symbol", how="left")
        strat = stratify_by_quantile(merged, "public_subscription_multiple", bins=3)
        strat_md = strat.to_markdown(index=False) if not strat.empty else ""

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    trades.to_csv(REPORTS_DIR / "trades.csv", index=False)
    metrics_payload = {
        "overall": overall,
        "by_version": by_version,
        "cost_sensitivity": {str(k): v for k, v in sensitivity.items()},
    }
    (REPORTS_DIR / "metrics.json").write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report_template(overall, REPORTS_DIR / "research_report.md",
                          by_version=by_version, sensitivity=sensitivity, coverage=coverage, stratification_md=strat_md)
    print(json.dumps(metrics_payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
