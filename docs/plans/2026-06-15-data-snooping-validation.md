# 设计 + 实现计划：Data-snooping-robust 验证层（2026-06-15）

> 状态：**设计已与用户确认 → TDD 实现中**
> 方向链：用户选「方法论框架」→「data-snooping 校正」→「稳健轻量组合」。

## 背景与目标

现有框架已含 bootstrap CI + 单策略置换检验，但**唯一仍敞着的过拟合口子是 data snooping**：
我们试了 baseline / improved / reversal 多个策略，并对 improved 扫了 6 档暗盘门槛
（`GREY_THRESHOLD_SWEEP=(0,0.1,0.2,0.3,0.5,1.0)`），然后报告/比较其中表现好的那个
（门槛 1.0 档 2 笔 +42.8% 看似最佳）。当前的单次 bootstrap / 置换检验**没有校正
「在一堆配置里挑了最好那个」带来的选择偏差**。本层补这个空白。

**本层只是"裁判"**：不产生新策略、不调参、不碰信号生成与执行引擎，只让结论更保守。

## 合规确认（对照要求文档）

- `strategy-project.md`：不碰无未来函数/成本/trade log/外部数据来源；只往 `metrics.json` 加键、报告加节。✅
- `grading-rubric.md` Red Flags：不触发任何一条；强化"解释假设/不过拟合/说明限制"。✅
- 项目 `CLAUDE.md`：只改 `strategy-project/src/{stats,backtest,report_tables}.py` + 测试，不碰固定脚手架。✅
- 全局 `CLAUDE.md`：pixi 环境、git author=rookiewu417、plan 存本目录；DSR 用标准库 `statistics.NormalDist`，**不引 scipy**。✅

## 三个方法（精确定义）

### (a) max-statistic 置换检验（White's Reality Check 风格）— 核心
- 池 `r` = baseline 动量信号池逐笔 return（`base_returns`，14 笔）。
- 候选 = grey sweep 6 档，各档选股数 `k_i`（=该门槛实际成交笔数）。
- `observed_best` = 实际 6 档里最大的复利 `total_return`。
- 每轮置换 b：随机排列池得 π_b；对每档算 `t_i = prod(1+π_b[:k_i]) − 1`；取 `M_b = max_i t_i`。
  （所有档共享同一排列 → 保留策略间相关性，RC 精髓。）
- `p = (#{M_b ≥ observed_best} + 1) / (B + 1)`（+1 平滑，避免 p=0）。
- 含义：候选越多，max-null 越大、p 越大——这就是对"挑最好"的惩罚。

### (b) Holm–Bonferroni step-down 校正 — 辅助
- 对 6 档各自的单边置换 p（从池随机选 k_i，≥ 该档 observed 的频率）做 Holm 校正。
- 排序 p_(1)≤…≤p_(m)，`p_(i)^adj = max_{j≤i} min(1, (m−j+1)·p_(j))`（enforce 单调、clip≤1）。
- 报告展示最小校正后 p（即"最显著的那档在多重校正后还剩多少显著性"）。

### (c) Deflated Sharpe Ratio（Bailey & López de Prado 2014）— 量化指标
- 对 **improved（门槛 0，12 笔，唯一不亏、被报告主推的改进版）** 算，笔数足以估偏度/峰度。
- `PSR(SR*) = Φ[ (ŜR − SR*)·√(T−1) / √(1 − γ̂₃·ŜR + ((γ̂₄−1)/4)·ŜR²) ]`
- `DSR = PSR(SR0)`，`SR0 = √V̂·[ (1−γ)·Z⁻¹(1−1/N) + γ·Z⁻¹(1−1/(N·e)) ]`
  （γ=0.5772 Euler–Mascheroni，V̂=试验间 Sharpe 方差，N=试验数，Z⁻¹=正态分位，用 `NormalDist.inv_cdf`）。
- ŜR、γ̂₃、γ̂₄、T 取自该策略 per-trade returns。
- **退化保护**：T<3 或 std=0 或分母≤0 → 返回 `None`，报告显示"N/A（样本太小）"。
- **诚实标注**：T 极小 → DSR 保守/不稳，仅作参考，主裁以 reality-check p 为准。

## N（试验次数）口径
- reality-check 的候选数 = 6（grey sweep 档）。
- DSR 的 N = 全局"看过的配置"保守下界 = `len(VERSIONS) + len(GREY_THRESHOLD_SWEEP)`（=3+6=9，含重叠，偏保守）。
- 报告注明：**不含历史已移除的 multifactor 及其 sweep；若计入 N 更大、惩罚更重、结论只会更保守**。

## 接入点

| 文件 | 改动 |
|---|---|
| `stats.py` | +`reality_check_pvalue(pool, ks, observed_best, *, n, seed)`、`holm_correction(pvalues)`、`deflated_sharpe_ratio(returns, n_trials, sharpe_variance)`；沿用 `seed=42` |
| `backtest.py` | 从 sweep 收集 `(k_i, total_return_i)`；算 reality_check_p / holm / DSR；写 `metrics.json` 新键 `data_snooping`（含 reality_check_p、holm_min_adjusted_p、deflated_sharpe、输入 n_trials/T/observed_best） |
| `report_tables.py` | 新增"多重检验 / Data-snooping 稳健性"小节 + 自动判语（沿用现有 verdict 风格） |

## 测试计划（TDD，扩 `test_stats.py`）
1. `reality_check_pvalue`：(a) 某档真有超额→p 小；(b) 纯随机→p 大；(c) **候选数增大→同一 observed 的 p 不减**（多重惩罚单调）；(d) seed 可复现。
2. `holm_correction`：与手算一致、单调非减、clip≤1、空输入安全。
3. `deflated_sharpe_ratio`：∈[0,1]；N 增大→DSR 减；T<3 / 零方差 → None（退化保护）。
4. 集成（`test_backtest_integration`）：`metrics.json` 含 `data_snooping` 键且为标准 JSON。
5. 报告（`test_report_tables`）：稳健性小节文本生成。

## 防过拟合纪律
- 本层无任何可调参数（B 次数、seed 固定）；不挑门槛、不改策略。
- 预期诚实结论：reality-check p 大 + DSR 低/NA → 进一步坐实"本样本无稳健 alpha"。

## 决策记录
- DSR 小样本局限**如实写进报告**，不淡化。
- N 用**自动保守下界 + 注明不含已移除 multifactor**，不硬编码历史试验数（可复现优先）。
- DSR 依赖用标准库 `statistics.NormalDist`，**不引 scipy**（守"最小依赖/无安装包"）。

## 进度（2026-06-15 完成）
- [x] TDD：扩 `test_stats`（+11）→ 红 → 实现 `stats` 三函数 → 绿（reality-check 单调性/可复现、Holm 手算一致、DSR 退化保护）。
- [x] 接入 `backtest`：`data_snooping_diagnostics` over grey sweep；`metrics.json` 加 `data_snooping` 键。
- [x] 接入 `report_tables`：「多重检验 / Data-snooping 稳健性」小节 + 自动判语（+2 测试）。
- [x] 重跑 backtest：两次逐字节幂等；`pixi run test` → **56 passed**。
- [x] **实证结果**：reality-check **p=0.138**、Holm 最小校正 **p=0.396**、**DSR=0.0**（observed_best=+42.8%，N=9）→ 表观最优可由 data-snooping 解释，**坐实本样本无稳健 alpha**。
- [x] 提交（不 push）。
