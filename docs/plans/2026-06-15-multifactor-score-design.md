# 设计 spec：multifactor_score（行情+暗盘 等权分位打分）

> 日期 2026-06-15 · 状态：**已实现并验证 → 因过拟合移除（本文件保留作决策记录）**

## 移除决策（2026-06-15）

经 4 道检验一致证伪（Spearman=−0.61 反向、门槛非单调、bootstrap 95% CI=[−35%, +219%] 含巨亏、置换 p=0.074 不显著），`multifactor_score` 的 +43.5% 确认为 8 笔小样本的**过拟合尖峰**、不构成可靠 alpha。按用户决定**移除该策略**（`strategy`/`config`/`backtest`/`report_tables` 及对应测试），回退到 baseline/improved/reversal 三版本。

**保留**：通用稳健性诊断 `stats.py`（bootstrap CI + 置换检验）+ 报告诊断表——对剩余策略仍有价值（如 improved 选股 p=0.507 揭示暗盘单因子≈随机）。本文件保留，记录"实现 → 检验 → 证伪 → 移除"的完整过程，这本身即是诚实研究的范例。

## 背景与目标

三版本对比显示 improved（单一暗盘阈值）是唯一不亏的，但暗盘单因子 Spearman = −0.12、区分力弱、对成本脆弱。目标是**用「首日量能 + 暗盘溢价」的等权分位打分替代单一暗盘阈值**，在不增加过拟合的前提下提升信号区分力，并诚实检验它是否真比单暗盘强。

非目标：不优化权重、不优化门槛、不堆因子、不追求回测数字最大化（文档 red flag）。

## 策略定义：`multifactor_score`

### 信号池
候选池 = baseline 首日动量信号（`first_day_return > 5%` 且 tradable day2），与 baseline/improved/reversal **同池**，保证可比。多因子在池内排序选优。

### 因子与综合分
- 量能因子：`first_day_turnover`（首日成交额）在**信号池横截面**的分位 `rank(pct=True)` ∈ (0,1]；先验方向：高=资金关注度高，假设利于短期延续。
- 暗盘因子：`grey_change_pct` 在信号池横截面的分位；缺暗盘者该分位为 NaN。
- **综合分 = 两个分位的可得均值**（`nanmean`）：暗盘缺失时只用量能分位（即"可得因子均值"，不填值）。

### 入场规则
- 主策略：综合分 `>= multifactor_min`（默认 `0.5`，池内 top 50%）入场。
- 受控实验：综合分门槛扫描 `{0.3, 0.5, 0.7}` + Spearman(综合分, 收益)，呈现单调性，**不挑最优门槛**。

### 执行（复用现有引擎，零改动）
day2 open 入场、持 3 日、止损 8%/止盈 20%、触发价+gap 成交、扣买卖费/滑点/最低费。仅新增 mask。

## 实现改动点

| 文件 | 改动 |
|---|---|
| `config.py` | 加 `multifactor_min=0.5`、`multifactor_turnover_field="first_day_turnover"`；`MULTIFACTOR_SWEEP=(0.3,0.5,0.7)` |
| `strategy.py` | 加 `multifactor_score(features)` helper（信号池内算分位+可得均值，返回 Series）+ `multifactor_mask(features, config)` |
| `backtest.py` | `VERSIONS` 加 `("multifactor_score", multifactor_mask)`；加 `multifactor_sweep` + `multifactor_return_analysis`（Spearman），结构对齐现有 grey sweep |
| `report_tables.py` | `_analysis` 加 multifactor bullet（含单调性/相关性诚实判据，复用现有稳健 verdict 逻辑）；Strategy Definition 加 multifactor 定义 |
| `metrics.json` | 自动含第 4 version + `multifactor_threshold_sweep` + `multifactor_score_spearman` |

### 打分 helper 关键逻辑（无歧义）
```
sub = features[baseline_signal]
t_pct = sub[turnover_field].rank(pct=True)          # NaN 保持 NaN
g_pct = sub["grey_change_pct"].rank(pct=True)       # 缺暗盘 -> NaN
score = nanmean([t_pct, g_pct]) 逐行                # 缺暗盘 -> 只用 t_pct
mask = (score >= multifactor_min)，映射回 features 全集 index（池外=False）
```

## 防过拟合纪律（直面 red flag）
- 等权、无权重拟合；门槛用无参数 0.5/分位，不优化。
- 量能方向用先验（高=好），不从数据选方向。
- 阈值扫描 + Spearman 诚实呈现：若综合分与收益**非单调/弱相关**，如实承认区分力有限（沿用暗盘 sweep 的稳健 verdict 逻辑）。
- 报告标注：12–14 笔小样本，结论置信区间宽；多因子相对单暗盘的优势若 <1 笔差异，不夸大。

## 对照与验收
- 新增为第 4 version，与 baseline / improved(单暗盘) / reversal 并排；保留 improved 作直接对照。
- 验收：`multifactor_score` 出现在对照表/cost_sensitivity/Analysis/metrics.json；阈值扫描与 Spearman 产出；pipeline 幂等；全套测试绿。
- 成功标准 ≠ "收益更高"，而是：**口径正确、无未来函数、诚实呈现多因子 vs 单暗盘的真实差异**（无论正负）。

## 测试计划（TDD）
1. `multifactor_score` helper：分位计算、可得因子均值（缺暗盘只用量能）、不填值。
2. `multifactor_mask`：池内 top 档选择、池外=False、缺暗盘股凭量能可入选。
3. 集成：第 4 version 进 trades.csv / by_version / cost_sensitivity；阈值扫描与 spearman 在 metrics.json。
4. 报告：Analysis 含 multifactor bullet。

## 默认参数（已与用户确认，可改）
量能=成交额 `turnover`（非成交量）；主门槛 `0.5`；横截面分位用全信号池（不分行业/月份，样本太小）。

## 实现结果（2026-06-15，TDD 完成）
- 已实现:`config`(multifactor_min/turnover_field/MULTIFACTOR_SWEEP) · `strategy`(multifactor_score/multifactor_mask) · `backtest`(VERSIONS 第 4 版 + multifactor_sweep + multifactor_return_analysis) · `report_tables`(Strategy Def + Analysis 稳健 verdict + sweep 表)。
- 测试 **42 passed**；pipeline 幂等；metrics.json 标准 JSON(jq OK)。
- **关键发现（防过拟合检验立功）**:主门槛 0.5 时 8 笔 +43.5%(pf 2.32)看似最佳,但 **Spearman(综合分,收益)=−0.61、门槛扫描非单调**(0.3→+0.9%、0.5→+43.5%、0.7→+0.2%)。综合分与收益**强负相关**+尖峰非单调 ⇒ +43.5% 是小样本过拟合假象,**不构成可靠 alpha**。Analysis/README 已如实标注(⚠️)。
- 成功标准达成:不是"收益更高",而是**诚实识破了一个诱人的假结果**——这正是 spec 设定的目标。

## 过拟合量化（2026-06-15 追加，回应"能否消除过拟合"）
- 结论:**不可消除,只可抑制/检测/量化**——根源是 8–14 笔 + 单一窗口(自由度 ≫ 样本),非方法。
- 新增 `stats.py`:`bootstrap_total_return_ci`(复利 total_return 的 95% CI,固定 seed) + `permutation_selection_pvalue`(从 baseline 池随机选 k 笔 vs 实际,单侧 p)。
- 接入 backtest(`total_return_ci`/`selection_pvalue`)+ 报告"稳健性诊断"表。测试 **47 passed**,幂等。
- 实证(本数据):multifactor +43.5% 的 **95% CI=[−35%, +219%]**(点估计无意义)、**选股 p=0.074**(不显著);improved 选股 **p=0.507**(暗盘单因子选股≈随机)。量化坐实多因子高收益是过拟合尖峰。
- 根治路径:多年/多市场样本外验证(lab 数据不具备)→ Next Steps。

## 风险与局限
- 单一普涨窗口 + 小样本，多因子极易过拟合——靠"等权/无优化门槛/先验方向"压制，但无法消除。
- 量能方向是假设，需受控扫描检验；若非单调则结论存疑。
- 暗盘覆盖 12/14，量能 14/14；"可得均值"缓解但未消除选择偏差。
