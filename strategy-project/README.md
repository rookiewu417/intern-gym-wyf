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

- **Baseline**（`baseline_first_day_momentum_daily`，照文档规则 1–8）：day1 `close/open-1 > 5%` → day2 open 入场 → 持 3 个交易日 → 止损 8% / 止盈 20% → 扣买卖费+滑点+最低费 → 每股票最多一笔。
- **Improved**（`improved_grey_market_filter`）：在 baseline 之上叠加**暗盘溢价过滤**（`grey_change_pct >= 阈值`），缺暗盘数据者不入场。
- **无未来函数**：信号仅用 day1 与上市前/上市时点外部数据（暗盘=上市前夜、超购=招股结束）；执行价用 day2 open。
- **停牌/缺失**：`daily_utils.normalize_daily` 标 `tradable`，不可交易日跳过、出场顺延，缺失保留 NaN（绝不填 0）。

## 外部数据（自行调研）

`data/external/ipo_info.csv`、`grey_market.csv`：暗盘涨幅/超购倍数/发行价/保荐人/行业等，**每行带 `source_url`，缺失留空不填 0**。覆盖率（grey 12/65、ipo-subscription 10/65）由 `coverage_summary` 与报告如实给出。

## 受控实验与结论（摘要）

- baseline 14 笔 −2.9%（pf 0.98）；improved（暗盘≥0）12 笔 +24.0%（pf 1.25）。
- **受控阈值扫描**（仅暗盘可得域，隔离数据可得性的选择偏差）：门槛 0→1 时平均单笔收益 +2.0% → +44.6%，Spearman(暗盘, 收益)=+0.38 —— 暗盘溢价对早期动量有**正向但尾部驱动**的区分力。
- 局限：单一普涨窗口、样本小、效应集中于少数极热标的。详见 `reports/research_report.md`（全自动生成，含 Analysis 与 Limitations）。

## 模块

`config`（参数）· `daily_utils`（归一化+tradable）· `external_data`（外部加载）· `costs`（费用/滑点/缩放）· `strategy`（统一回测引擎+masks）· `metrics`（指标+分版本）· `report_tables`（表格+报告生成）· `plots`（图表）· `backtest`（编排）。

## 测试

`pixi run test` —— 覆盖无未来函数、成本/滑点、停牌跳过、持仓窗口上界、回撤口径、暗盘过滤、外部覆盖率、阈值扫描与图表产出。
