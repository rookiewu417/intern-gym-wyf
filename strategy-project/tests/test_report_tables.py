import pandas as pd
from report_tables import _analysis, comparison_table, grey_sweep_table, robustness_table, sensitivity_table, stratify_by_quantile

_BY_VER = {
    "baseline_first_day_momentum_daily": {"trade_count": 14, "win_rate": 0.28, "total_return": -0.15, "profit_factor": 0.93},
    "improved_grey_market_filter": {"trade_count": 12, "win_rate": 0.33, "total_return": 0.01, "profit_factor": 1.16},
}


def test_analysis_cautious_when_non_monotone_or_negative_corr():
    # 首尾看似上升，但中间为负（非单调）、末档塌缩到 2 笔、全样本 corr 为负 → 不能下强结论
    sweep = {
        0.0: {"average_return": 0.009, "trade_count": 12},
        0.1: {"average_return": -0.001, "trade_count": 10},
        0.3: {"average_return": -0.014, "trade_count": 8},
        1.0: {"average_return": 0.195, "trade_count": 2},
    }
    text = _analysis(_BY_VER, sweep, grey_corr=-0.12)
    assert "区分力来自信号本身" not in text
    assert "有限" in text


def test_grey_sweep_table_shows_infinity_symbol():
    # profit_factor 无亏损=inf：报告显示 ∞（metrics.json 另记为 null），不显示误导性的 "inf"
    sweep = {0.0: {"trade_count": 2, "win_rate": 1.0, "average_return": 0.2, "total_return": 0.44, "profit_factor": float("inf")}}
    md = grey_sweep_table(sweep)
    assert "∞" in md and "inf" not in md


def test_analysis_includes_reversal_when_present():
    by_ver = {
        "baseline_first_day_momentum_daily": {"trade_count": 14, "win_rate": 0.28, "total_return": -0.15, "profit_factor": 0.93},
        "reversal_first_day_daily": {"trade_count": 5, "win_rate": 0.4, "total_return": 0.1, "profit_factor": 1.2},
    }
    text = _analysis(by_ver, {}, grey_corr=float("nan"))
    assert "Reversal" in text


def test_analysis_confident_when_monotone_and_positive_corr():
    sweep = {
        0.0: {"average_return": 0.01, "trade_count": 12},
        0.1: {"average_return": 0.03, "trade_count": 9},
        0.3: {"average_return": 0.06, "trade_count": 6},
        1.0: {"average_return": 0.12, "trade_count": 4},
    }
    text = _analysis(_BY_VER, sweep, grey_corr=0.5)
    assert "区分力来自信号本身" in text

def test_comparison_table_lists_versions():
    by_ver = {
        "baseline_first_day_momentum_daily": {"trade_count": 5, "win_rate": 0.4, "total_return": 0.1, "max_drawdown": -100, "average_holding_days": 2.0, "profit_factor": 1.2},
        "improved_grey_market_filter": {"trade_count": 2, "win_rate": 0.5, "total_return": 0.2, "max_drawdown": -50, "average_holding_days": 2.0, "profit_factor": 1.5},
    }
    md = comparison_table(by_ver)
    assert "baseline_first_day_momentum_daily" in md and "improved_grey_market_filter" in md
    assert "trade_count" in md

def test_sensitivity_table_lists_scales():
    rows = {0.5: {"total_return": 0.3}, 1.0: {"total_return": 0.2}, 2.0: {"total_return": 0.0}}
    md = sensitivity_table(rows)
    assert "0.5" in md and "2.0" in md

def test_robustness_table_has_ci_and_pvalue():
    by_ver = {"improved_grey_market_filter": {"total_return": 0.009}, "baseline_first_day_momentum_daily": {"total_return": -0.15}}
    ci = {"improved_grey_market_filter": [-0.3, 0.9], "baseline_first_day_momentum_daily": [-0.5, 0.1]}
    pval = {"improved_grey_market_filter": 0.42}  # baseline 无选股 p
    md = robustness_table(by_ver, ci, pval)
    assert "95% CI" in md and "0.42" in md
    assert "improved_grey_market_filter" in md


def test_stratify_by_quantile_groups():
    trades = pd.DataFrame({"return": [0.1, 0.2, -0.1, 0.05], "public_subscription_multiple": [10, 200, 5, 150]})
    out = stratify_by_quantile(trades, "public_subscription_multiple", bins=2)
    assert len(out) >= 1
    assert "count" in out.columns and "avg_return" in out.columns
