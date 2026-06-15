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

    features = pd.DataFrame([
        {"symbol": "1.HK", "coverage_start": "20260102", "entry_date": "20260105",
         "baseline_signal": True, "reversal_signal": False, "grey_change_pct": 0.2, "premium_to_ipo_price": 0.2,
         "public_subscription_multiple": 50.0, "first_day_turnover": 5000.0},
        {"symbol": "9.HK", "coverage_start": "20260102", "entry_date": "20260106",
         "baseline_signal": False, "reversal_signal": True, "grey_change_pct": None, "premium_to_ipo_price": None,
         "public_subscription_multiple": None, "first_day_turnover": 3000.0},
    ])
    features.to_parquet(processed / "features.parquet", index=False)
    daily = pd.DataFrame([
        {"symbol": "1.HK", "trade_date": "20260105", "open": 100, "high": 105, "low": 99, "close": 102, "volume": 10, "turnover": 1, "previous_close": 100, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260106", "open": 102, "high": 108, "low": 101, "close": 107, "volume": 10, "turnover": 1, "previous_close": 102, "suspend_flag": 0},
        {"symbol": "1.HK", "trade_date": "20260107", "open": 107, "high": 110, "low": 104, "close": 109, "volume": 10, "turnover": 1, "previous_close": 107, "suspend_flag": 0},
        {"symbol": "9.HK", "trade_date": "20260105", "open": 100, "high": 100, "low": 70, "close": 80, "volume": 10, "turnover": 1, "previous_close": 120, "suspend_flag": 0},
        {"symbol": "9.HK", "trade_date": "20260106", "open": 80, "high": 95, "low": 79, "close": 90, "volume": 10, "turnover": 1, "previous_close": 80, "suspend_flag": 0},
        {"symbol": "9.HK", "trade_date": "20260107", "open": 90, "high": 99, "low": 88, "close": 96, "volume": 10, "turnover": 1, "previous_close": 90, "suspend_flag": 0},
    ])
    daily.to_parquet(raw / "daily_bars.parquet", index=False)
    (raw / "cost_model.json").write_text(json.dumps({"buy_cost_bps": 12, "sell_cost_bps": 22, "slippage_bps": 10, "min_fee": 5}), encoding="utf-8")
    (raw / "coverage_summary.json").write_text(json.dumps({"symbol_count": 1}), encoding="utf-8")

    backtest.main()

    ALL_VERSIONS = {"baseline_first_day_momentum_daily", "improved_grey_market_filter",
                    "reversal_first_day_daily"}
    trades = pd.read_csv(reports / "trades.csv")
    assert set(trades["strategy_version"]) <= ALL_VERSIONS
    assert "reversal_first_day_daily" in set(trades["strategy_version"])  # reversal 对照已纳入
    raw_metrics = (reports / "metrics.json").read_text()
    assert "Infinity" not in raw_metrics and "NaN" not in raw_metrics  # 标准 JSON（inf/nan → null）
    metrics = json.loads((reports / "metrics.json").read_text())
    assert "by_version" in metrics and "cost_sensitivity" in metrics
    assert "overall" not in metrics  # 去掉对 baseline 与其子集 improved 的重复计数 union
    assert "reversal_first_day_daily" in metrics["by_version"]
    assert "total_return_ci" in metrics and "improved_grey_market_filter" in metrics["total_return_ci"]
    assert len(metrics["total_return_ci"]["improved_grey_market_filter"]) == 2  # (lo, hi)
    assert "selection_pvalue" in metrics and "improved_grey_market_filter" in metrics["selection_pvalue"]
    cs = metrics["cost_sensitivity"]
    assert set(cs) <= ALL_VERSIONS and "reversal_first_day_daily" in cs
    for scales in cs.values():
        assert set(scales) == {"0.5", "1.0", "2.0"}
    assert "external_coverage" in metrics
    assert metrics["external_coverage"]["external_grey_coverage_ratio"] == 0.5  # 2 标的，1 有暗盘
    # 信号标的口径：momentum 信号只有 1.HK，且有暗盘 -> 1.0（比 universe 分母 0.5 更贴近策略）
    assert metrics["external_coverage"]["external_signal_symbols_total"] == 1
    assert metrics["external_coverage"]["external_grey_coverage_on_signals"] == 1.0
    assert "grey_threshold_sweep" in metrics
    assert (reports / "research_report.md").exists()
    assert (reports / "equity_curve.png").exists()
    assert (reports / "grey_threshold_sweep.png").exists()
    report_text = (reports / "research_report.md").read_text()
    assert "买入 12bps" in report_text and "卖出 22bps" in report_text  # 报告列出具体成本数值
    # data-snooping 验证层：metrics 含诊断键 + 报告含多重检验小节
    assert "data_snooping" in metrics
    ds = metrics["data_snooping"]
    assert "reality_check_pvalue" in ds and "deflated_sharpe_ratio" in ds
    assert "Data-snooping" in report_text
