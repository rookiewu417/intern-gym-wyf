# Strategy Project: IPO / New Listing Daily Research

复现并改进港股新股「首日动量 → 后续数日收益」的日线策略，扣成本评估可交易性，并用自行调研的暗盘/IPO 外部数据做过滤与分层。依据 `docs/strategy-project.md`。

## 环境（pixi）

仓库根已配置 `pixi.toml`。常用任务（均从仓库根运行）：

```bash
pixi install            # 一次性安装环境
pixi run serve-research # 启动日线 HTTP API (:9041)
pixi run download       # 从 API 下载到 data/raw（含 coverage_summary.json）
pixi run features       # 生成 data/processed/features.parquet
pixi run backtest       # 生成 reports/{trades.csv,metrics.json,research_report.md,*.png}
pixi run pipeline       # 离线串联（--source-root ../research-data，无需起服务）
pixi run test           # 策略 + research-api 测试
```

> 若本机有 HTTP 代理拦截 localhost，`download`/`test` 任务已内置 `NO_PROXY=127.0.0.1,localhost`。

## 策略

- **Baseline**（`baseline_first_day_momentum_daily`，照文档规则 1–8）：day1 `close/open-1 > 5%` → day2 open 入场 → 持 3 个交易日 → 止损 8% / 止盈 20%（触发按 `stop_level`/`take_level` 成交，跳空越过则按当日 open）→ 扣买卖费+滑点+最低费 → 每股票最多一笔。
- **Improved**（`improved_grey_market_filter`）：在 baseline 之上叠加**暗盘溢价过滤**（`grey_change_pct >= 阈值`），缺暗盘数据者不入场。
- **Reversal**（`reversal_first_day_daily`，对照）：首日大跌（`close/open-1 < −5%`）后预期反转，day2 open 做多，其余执行同 baseline；与 momentum 互斥（文档要求保留 momentum 作对照）。
- **Improved+Trailing**（`improved_trailing_stop`，增强）：improved 选股不变，**出场改用追踪止损**（自移动高点回撤 10% 才出、让趋势跑，不固定 20% 封顶；进入当日用昨日高点判触发，无 look-ahead），最大持仓放宽到 10 日。
- **无未来函数**：信号仅用 day1 与上市前/上市时点外部数据（暗盘=上市前夜、超购=招股结束）；执行价用 day2 open。
- **停牌/缺失**：`daily_utils.normalize_daily` 标 `tradable`，不可交易日跳过、出场顺延，缺失保留 NaN（绝不填 0）。

## 外部数据（自行调研）

`data/external/ipo_info.csv`、`grey_market.csv`：暗盘涨幅/超购倍数/发行价/保荐人/行业等，**每行带 `source_url`，缺失留空不填 0**。覆盖率按两种口径如实给出：universe 全集（grey 12/65、ipo 10/65）与**信号标的**（grey 12/14 ≈ 85.7%，更贴近策略实际用到的覆盖）。

## 受控实验与结论（摘要）

- baseline 14 笔 −15.3%（pf 0.93）；improved（暗盘≥0）12 笔 +0.9%（pf 1.16）；reversal（对照）27 笔 −11.5%（pf 1.04）；**improved+trailing（追踪止损增强）12 笔 +112.6%（pf 2.70、win 41.7%）**。口径：`total_return` 为序贯等额下注的**复利**收益、`max_drawdown` 为复利权益的**百分比**回撤；reversal 与 momentum 互斥、improved 及 improved+trailing 为 baseline 选股子集，各版本分列不合并计数。
- **受控阈值扫描**（仅暗盘可得域，隔离数据可得性的选择偏差）：门槛 0→1 时平均单笔收益 +0.9% → +19.5%（首尾上升但**非单调**、末档仅 2 笔），全样本 Spearman(暗盘, 收益)=**−0.12**。止盈/止损按触发价位成交后（不再用 close 高估热门标的收益），暗盘溢价的稳健区分力**有限**，naive 对照优势主要来自『能查到暗盘≈热门股』的选择效应与少数极热标的。
- **稳健性诊断（Bootstrap CI + 置换检验）**：所有策略 total_return 的 95% CI 都极宽（improved [−55%, +124%]、baseline [−62%, +88%]），improved 选股置换 **p=0.507**——暗盘单因子选股不比随机选同等数量更好。
- **Data-snooping 校正（White RC + Holm + Deflated Sharpe）**：量化"试了 N=14 个配置挑最好"的选择偏差——reality-check **p=0.138**、Holm 最小校正 **p=0.396**、**DSR=0.0**：**选股因子**经多重检验后仍不显著。**出场机制**上 improved+trailing 回测 +112.6% 且随 trail **单调**（机制性、非尖峰），但靠单一普涨窗口"让趋势跑"天然占优，外推到下跌/震荡市存疑——需多市场样本外验证。
- **过拟合不可"消除"只可量化**：根源是 8–14 笔样本 + 单一普涨窗口（自由度远超样本），不是方法。曾试「量能+暗盘」多因子打分，门槛 0.5 一度回测 +43.5%，但同一套检验（Spearman=−0.61、门槛非单调、置换 p=0.074）证伪为过拟合尖峰，**已移除**。根治需多年多市场样本外数据（lab 不具备，列入 Next Steps）。
- 局限：单一普涨窗口、样本小、效应集中于少数极热标的。详见 `reports/research_report.md`（全自动生成，含 Analysis 与 Limitations）。

## 模块

`config`（参数）· `daily_utils`（归一化+tradable）· `external_data`（外部加载）· `costs`（费用/滑点/缩放）· `strategy`（统一回测引擎+masks，固定止盈/止损 + 追踪止损）· `metrics`（指标+分版本）· `stats`（bootstrap CI + 置换 + reality-check/Holm/Deflated Sharpe）· `report_tables`（表格+报告生成）· `plots`（图表）· `backtest`（编排）。

## 测试

`pixi run test`（59 项）—— 覆盖无未来函数、成本/滑点/最低费、止损止盈触发价与跳空成交、**追踪止损（回撤触发/让赢家跑/无 look-ahead）**、停牌跳过、持仓窗口上界、复利回撤含初始资金、profit_factor 无亏损=∞、暗盘过滤、reversal 信号、bootstrap CI 与置换检验、**reality-check 多重惩罚单调性 / Holm / Deflated Sharpe 退化保护**、外部覆盖率（含信号标的口径）、阈值扫描稳健判据、标准 JSON 与图表产出。
