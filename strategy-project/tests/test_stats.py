from stats import (
    bootstrap_total_return_ci,
    deflated_sharpe_ratio,
    holm_correction,
    permutation_selection_pvalue,
    reality_check_pvalue,
)


def test_bootstrap_ci_degenerate_when_returns_identical():
    # 全相同收益 -> 任何重采样 total 都相同 -> CI 退化为一个点
    lo, hi = bootstrap_total_return_ci([0.1, 0.1, 0.1], n=200, seed=1)
    point = 1.1 ** 3 - 1
    assert abs(lo - point) < 1e-9 and abs(hi - point) < 1e-9


def test_bootstrap_ci_brackets_point_estimate():
    rets = [0.2, -0.1, 0.15, -0.08, 0.3]
    point = 1.0
    for r in rets:
        point *= (1 + r)
    point -= 1
    lo, hi = bootstrap_total_return_ci(rets, n=2000, seed=7)
    assert lo <= point <= hi
    assert lo < hi  # 非退化区间


def test_permutation_pvalue_small_when_selection_is_best_possible():
    # pool: 5 个 +1.0, 5 个 -0.5；observed = 恰好选中全部 5 个 +1.0（最大可能）-> p 极小
    pool = [1.0] * 5 + [-0.5] * 5
    observed = (2.0 ** 5) - 1
    p = permutation_selection_pvalue(pool, k=5, observed_total=observed, n=2000, seed=3)
    assert p < 0.05


def test_permutation_pvalue_large_when_selection_is_typical():
    # observed = 平均水平的一正一负组合 -> 随机选也常达到 -> p 大
    pool = [0.1, 0.1, -0.1, -0.1]
    observed = 1.1 * 0.9 - 1
    p = permutation_selection_pvalue(pool, k=2, observed_total=observed, n=2000, seed=3)
    assert p > 0.3


# --- data-snooping 验证层：reality check（max-statistic 置换）+ Holm + deflated Sharpe ---

def test_reality_check_small_when_best_candidate_is_extreme():
    # 池 3 个 +1.0、7 个 -0.5；唯一候选选 3 笔，observed=选中全部 +1.0（极端最优）-> p 小
    pool = [1.0] * 3 + [-0.5] * 7
    observed_best = 2.0 ** 3 - 1
    p = reality_check_pvalue(pool, ks=[3], observed_best=observed_best, n=2000, seed=3)
    assert p < 0.05


def test_reality_check_large_when_best_candidate_is_typical():
    # observed 平庸（介于组合值之间）-> 随机的 max 常超过 -> p 大
    pool = [0.1, 0.1, -0.1, -0.1]
    observed_best = -0.05
    p = reality_check_pvalue(pool, ks=[2, 2], observed_best=observed_best, n=2000, seed=3)
    assert p > 0.3


def test_reality_check_penalizes_more_candidates():
    # 同池、同 observed_best、同 seed：候选越多（不同 k 子集）-> 每轮 max 不减 -> p 不减
    pool = [0.3, 0.2, 0.1, -0.1, -0.2, -0.3, 0.05, -0.05]
    observed_best = 0.15
    p_few = reality_check_pvalue(pool, ks=[3], observed_best=observed_best, n=3000, seed=11)
    p_many = reality_check_pvalue(pool, ks=[3, 5, 7], observed_best=observed_best, n=3000, seed=11)
    assert p_many >= p_few


def test_reality_check_reproducible_with_seed():
    pool = [0.2, -0.1, 0.15, -0.08, 0.3, -0.2]
    a = reality_check_pvalue(pool, ks=[2, 4], observed_best=0.2, n=1000, seed=42)
    b = reality_check_pvalue(pool, ks=[2, 4], observed_best=0.2, n=1000, seed=42)
    assert a == b


def test_holm_correction_matches_manual():
    # m=3，sorted 0.01,0.03,0.04 -> adj 0.03,0.06,0.06
    adj = holm_correction({"a": 0.01, "b": 0.04, "c": 0.03})
    assert abs(adj["a"] - 0.03) < 1e-12
    assert abs(adj["c"] - 0.06) < 1e-12
    assert abs(adj["b"] - 0.06) < 1e-12


def test_holm_correction_monotone_and_clipped():
    adj = holm_correction({"x": 0.5, "y": 0.8})
    assert all(0.0 <= v <= 1.0 for v in adj.values())
    assert adj["x"] == 1.0 and adj["y"] == 1.0  # 2*0.5 封顶到 1.0


def test_holm_correction_empty_safe():
    assert holm_correction({}) == {}


def test_deflated_sharpe_in_unit_interval():
    rets = [0.2, -0.1, 0.15, -0.08, 0.3, -0.05, 0.12, -0.2, 0.05, 0.18, -0.12, 0.22]
    dsr = deflated_sharpe_ratio(rets, n_trials=9, sharpe_variance=0.25)
    assert dsr is not None and 0.0 <= dsr <= 1.0


def test_deflated_sharpe_decreases_with_more_trials():
    rets = [0.2, -0.1, 0.15, -0.08, 0.3, -0.05, 0.12, -0.2, 0.05, 0.18, -0.12, 0.22]
    few = deflated_sharpe_ratio(rets, n_trials=2, sharpe_variance=0.25)
    many = deflated_sharpe_ratio(rets, n_trials=100, sharpe_variance=0.25)
    assert few is not None and many is not None
    assert many <= few


def test_deflated_sharpe_none_when_too_few_trades():
    assert deflated_sharpe_ratio([0.1, 0.2], n_trials=9, sharpe_variance=0.25) is None


def test_deflated_sharpe_none_when_zero_variance():
    assert deflated_sharpe_ratio([0.1, 0.1, 0.1, 0.1], n_trials=9, sharpe_variance=0.25) is None
