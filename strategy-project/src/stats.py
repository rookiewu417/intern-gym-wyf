from __future__ import annotations

import math
from collections.abc import Iterable
from statistics import NormalDist

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


def reality_check_pvalue(
    pool_returns: Iterable[float], ks: Iterable[int], observed_best: float,
    *, n: int = 1000, seed: int = 42,
) -> float:
    """max-statistic 置换检验（White's Reality Check 风格）的 data-snooping p 值。

    每轮重排候选池，对每个候选选股数 k_i 取重排后前 k_i 笔算复利 total_return，
    取该轮所有候选的 max 构成 null 分布；p=(#{max>=observed_best}+1)/(n+1)（+1 平滑）。
    候选越多/k 越分散 → max-null 越大、p 越大，即对「在一堆配置里挑最好」的多重检验惩罚。
    """
    r = np.asarray(list(pool_returns), dtype=float)
    k_list = [int(k) for k in ks if 0 < int(k) <= r.size]
    if r.size == 0 or not k_list:
        return float("nan")
    rng = np.random.default_rng(seed)
    ge = 0
    for _ in range(n):
        perm = rng.permutation(r)  # 每轮一次重排，与候选数无关 → 跨候选共享随机源、保留相关性
        m = max(float(np.prod(1.0 + perm[:k]) - 1.0) for k in k_list)
        if m >= observed_best - 1e-12:
            ge += 1
    return float((ge + 1) / (n + 1))


def holm_correction(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm–Bonferroni step-down 多重检验校正：返回每个 key 的校正后 p（单调非减、clip≤1）。"""
    if not pvalues:
        return {}
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(items)
    adj: dict[str, float] = {}
    running = 0.0
    for i, (key, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * float(p)))  # step-down + enforce 单调
        adj[key] = running
    return adj


def deflated_sharpe_ratio(
    returns: Iterable[float], n_trials: int, sharpe_variance: float,
) -> float | None:
    """Deflated Sharpe Ratio (Bailey & López de Prado 2014)。

    扣除「试了 n_trials 次挑最好」的选择偏差后，观测 Sharpe 是否显著。返回 ∈[0,1]
    （越低越疑过拟合）；样本太小(<3)/零方差/分母非正 → None（小样本退化保护）。
    """
    r = np.asarray(list(returns), dtype=float)
    t = r.size
    if t < 3 or n_trials < 1:
        return None
    sd = float(r.std(ddof=1))
    if sd <= 0:
        return None
    sr = float(r.mean()) / sd                       # 非年化 per-trade Sharpe
    z = (r - r.mean()) / sd
    g3 = float(np.mean(z ** 3))                     # 偏度
    g4 = float(np.mean(z ** 4))                     # 峰度（正态=3）
    denom = 1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr ** 2
    if denom <= 0:
        return None
    nd = NormalDist()
    euler = 0.5772156649015329                      # Euler–Mascheroni γ
    var = max(float(sharpe_variance), 0.0)
    if var <= 0 or n_trials == 1:
        sr0 = 0.0                                   # 无多试验信息 → 不抬高门槛
    else:
        sr0 = math.sqrt(var) * (
            (1.0 - euler) * nd.inv_cdf(1.0 - 1.0 / n_trials)
            + euler * nd.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
        )
    return float(nd.cdf((sr - sr0) * math.sqrt(t - 1) / math.sqrt(denom)))
