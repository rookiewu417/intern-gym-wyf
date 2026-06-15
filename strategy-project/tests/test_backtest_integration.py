import json
import pandas as pd
import backtest

def test_run_backtest_writes_outputs(tmp_path, monkeypatch):
    # 构造最小 features + daily，落到临时 RAW/PROCESSED/REPORTS
    raw, processed, reports = tmp_path / "raw", tmp_path / "processed", tmp_path / "reports"
    for d in (raw, processed, reports):
        d.mkdir()
    monkeypatch.setattr(backtest, "RAW_DIR", raw)
    monkeypatch.setattr(backtest, "PROCESSED_DIR", processed)
    monkeypatch.setattr(backtest, "REPORTS_DIR", reports)

    features = pd.DataFrame([{
        "symbol": "1.HK", "coverage_start": "20260102", "entry_date": "20260105",
        "baseline_signal": True, "grey_change_pct": 0.2, "premium_to_ipo_price": 0.2,
        "public_subscription_multiple": 50.0,
    }])
    features.to_parquet(processed / "features.parquet", index=False)
    daily = pd.DataFrame([
        {"symbol": "1.HK", "trade_date": "20260105", "open": 100, "high": 105, "low": 99, "close": 102, "volume": 10, "turnover": 1, "previous_close": 100, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260106", "open": 102, "high": 108, "low": 101, "close": 107, "volume": 10, "turnover": 1, "previous_close": 102, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260107", "open": 107, "high": 110, "low": 104, "close": 109, "volume": 10, "turnover": 1, "previous_close": 107, "suspend_flag": 0},
    ])
    daily.to_parquet(raw / "daily_bars.parquet", index=False)
    (raw / "cost_model.json").write_text(json.dumps({"buy_cost_bps": 12, "sell_cost_bps": 22, "slippage_bps": 10, "min_fee": 5}), encoding="utf-8")
    (raw / "coverage_summary.json").write_text(json.dumps({"symbol_count": 1}), encoding="utf-8")

    backtest.main()

    trades = pd.read_csv(reports / "trades.csv")
    assert set(trades["strategy_version"]) <= {"baseline_first_day_momentum_daily", "improved_grey_market_filter"}
    metrics = json.loads((reports / "metrics.json").read_text())
    assert "by_version" in metrics and "overall" in metrics and "cost_sensitivity" in metrics
    assert "external_coverage" in metrics
    assert metrics["external_coverage"]["external_grey_coverage_ratio"] == 1.0
    assert metrics["external_coverage"]["external_ipo_coverage_ratio"] == 1.0
    assert (reports / "research_report.md").exists()
