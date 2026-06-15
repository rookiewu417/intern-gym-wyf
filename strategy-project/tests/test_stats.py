from stats import bootstrap_total_return_ci, permutation_selection_pvalue


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
