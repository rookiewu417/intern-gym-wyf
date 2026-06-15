from __future__ import annotations

from collections.abc import Iterable

import numpy as np


def bootstrap_total_return_ci(
    returns: Iterable[float], *, n: int = 1000, seed: int = 42, alpha: float = 0.05
) -> tuple[float, float]:
    """对逐笔 return 有放回重采样，给序贯复利 total_return 的 (lo, hi) CI。seed 固定→可复现。"""
    r = np.asarray(list(returns), dtype=float)
    if r.size == 0:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, r.size, size=(n, r.size))
    boots = np.prod(1.0 + r[idx], axis=1) - 1.0
    return (float(np.quantile(boots, alpha / 2)), float(np.quantile(boots, 1 - alpha / 2)))


def permutation_selection_pvalue(
    pool_returns: Iterable[float], k: int, observed_total: float, *, n: int = 1000, seed: int = 42
) -> float:
    """单侧置换 p：从候选池随机选 k 笔，其复利 total_return >= 实际值的频率。

    检验「按因子选出的 k 笔」是否优于「随机选 k 笔」。p 大 = 选股不比随机好（疑过拟合/噪声）。
    """
    r = np.asarray(list(pool_returns), dtype=float)
    if r.size == 0 or k <= 0 or k > r.size:
        return float("nan")
    rng = np.random.default_rng(seed)
    ge = 0
    for _ in range(n):
        sample = rng.choice(r, size=k, replace=False)
        if float(np.prod(1.0 + sample) - 1.0) >= observed_total - 1e-12:
            ge += 1
    return float(ge / n)
