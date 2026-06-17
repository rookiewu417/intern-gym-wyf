# Market Terminal Internship Lab

这是一个独立的招聘 / 实习生练习仓库骨架，内置一套固定的 mock 基础设施 + 裁剪样本数据，拆分出**三个相互独立的候选人项目**。目标不是复刻完整生产系统，而是让候选人在可控沙箱里处理我们真实遇到过的问题：实时数据刷新、券商队列语义、effective-day 对齐、旧数据 fallback、移动端展示，以及日线策略研究流程。

## 三个项目

| 项目 | 目标 | 数据源 | 主要交互 | README |
|---|---|---|---|---|
| `frontend-project` | **Market Terminal Lite** —— 轻量行情终端页面（K 线 / 成交量 / 大额交易 / 券商队列 / 10·100·1000 档切换 / 重连） | `mock-feed`（WebSocket :9021） | 浏览器前端（Vite :5176） | [frontend-project/README.md](frontend-project/README.md) |
| `backend-project` | **Market State Engine Lite** —— 用 `mock-xtquant` SDK 实现实时状态引擎，按 `terminal-message-v3` 输出 snapshot/delta | `mock-xtquant` SDK + `sample-data` | 自建 WebSocket（:9031） | [backend-project/README.md](backend-project/README.md) |
| `strategy-project` | **IPO / New Listing Daily Research** —— 港股新股首日动量日线策略，扣成本评估、外部暗盘数据过滤与稳健性检验 | `mock-research-api`（HTTP :9041） + `research-data` | 离线回测管线（pixi） | [strategy-project/README.md](strategy-project/README.md) |

> 候选人 fork 后**完成其中一个**。每个项目自带任务说明、运行方式与提交清单。

**本仓库实现进度**：`backend-project` 已在本分支完整实现（**40 个测试全绿**，端到端真实订阅集成）——提交说明见 [backend-project/SUBMISSION.md](backend-project/SUBMISSION.md)。`strategy-project` 为可运行 scaffold 并已附完整研究结论；`frontend-project` 的任务骨架见其目录。

## 两个数据面 / 两个服务器（不要混用）

| 数据面 | 数据 | 服务器 | 消费方 | 粒度 |
|---|---|---|---|---|
| **Realtime** | `sample-data/` | `mock-feed`（WS :9021）与 `mock-xtquant` SDK | 前端 + 后端 | 日内（1m / ticks / broker queue） |
| **Research** | `research-data/` | `mock-research-api`（HTTP :9041） | 策略 | 日线 + 成本模型 |

⚠️ **两套日线数据不要混**：`sample-data/silver_daily_bars_v1.csv`（仅 OHLCV，5 支实时股，用于前/后端的大额交易 baseline）≠ `research-data/daily_bars.parquet`（65 支、额外含 `previous_close`/`suspend_flag`，仅策略用）。

前后端默认样本股票：

```text
02723.HK, 02675.HK, 00100.HK, 02513.HK, 06082.HK
```

## 端口

| 端口 | 服务 |
|---|---|
| `9021` | mock-feed（前端用的浏览器 WebSocket） |
| `9031` | backend-project 实现的状态引擎 WebSocket |
| `9041` | mock-research-api（策略用的日线 HTTP API） |
| `5176` | 前端 Vite dev server |

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
make install
make smoke            # 回放一小段 mock subscription，打印 callback_count => mock 数据路径 OK
```

按项目分别运行（均从仓库根目录）：

```bash
# 前端：先起浏览器 mock feed，再起 Vite
make serve                      # ws://127.0.0.1:9021/ws
cd frontend-project && npm install && npm run dev   # http://127.0.0.1:5176

# 后端：本仓库已实现的状态引擎
make serve-backend              # ws://127.0.0.1:9031/ws

# 策略：日线 HTTP API + 离线回测（pixi）
make serve-research             # http://127.0.0.1:9041
pixi run pipeline               # download -> features -> backtest（或加 --source-root ../research-data 跳过 API）
```

Docker 方式：

```bash
docker compose up --build
```

`sample-data` 已随仓库提供；维护者重裁数据包时再运行 `make build-data SILVER_ROOT=/path/to/full/silver-root`。

## 测试

```bash
make test            # 全量 pytest（backend + research-api + strategy）
```

各项目独立测试：后端 `pytest backend-project/tests`（40）；策略 `pixi run test`（63）；前端 `cd frontend-project && npm run test`（Vitest）。

> 注：策略回测依赖 `matplotlib`（出图）；若用根 `.venv` 跑 `make test` 而未装该依赖，strategy 的集成测试会在收集阶段报 `ModuleNotFoundError`——策略环境请用 `pixi`（`pixi run test`）。

## What Is Included

```text
mock-xtquant/       xtquant.xtdata 兼容 mock SDK（后端候选人用）
mock-feed/          浏览器可连接的 WebSocket mock feed（前端候选人用，亦是后端的可执行规范参考）
mock-research-api/  策略项目使用的日线历史 HTTP API
research-data/      策略 HTTP API 使用的日线-only 数据包
sample-data/        5 支股票的裁剪样本数据（实时面）
frontend-project/   前端任务说明和骨架
backend-project/    后端任务说明 + 已实现的状态引擎
strategy-project/   策略研究项目可运行 scaffold
docs/               总览、任务说明、接口契约、数据说明、评分标准
scripts/            维护者样本数据裁剪脚本
examples/           mock xtdata smoke 示例
```

## Candidate Workflow

1. Fork 或新建分支。
2. 按对应项目的 README 完成**一个**项目。
3. 提交 PR，说明：实现了什么 / 如何运行 / 如何验证 / 已知限制。

## Boundaries

不要在练习中接入真实 xtquant、Redis、Kafka 或生产 token。前后端练习的数据源固定为 `mock-xtquant + sample-data`；策略练习的数据源固定为 `mock-research-api + research-data`。

分层责任：

- `mock-xtquant` 模拟 SDK，暴露接近原始样本的数据语义；后端候选人需自行处理 effective-day、状态机和 contract 输出。
- `mock-feed` 是给前端候选人的浏览器 WebSocket，输出 contract-compliant snapshot/delta；broker queue 只能用旧日期 fallback 时会在 payload 显式标记。
- `mock-research-api` 是给策略候选人的日线历史 HTTP API，只提供 IPO universe coverage、daily bars 和 cost model；IPO / 暗盘资料由候选人自行调研。
- `backend-project` 是候选后端实现入口，不应依赖真实生产服务。

## 文档

- 文档索引：[docs/README.md](docs/README.md)
- 前后端共享语义 + WS 契约 + 评分：[docs/frontend-backend-projects.md](docs/frontend-backend-projects.md)
- WS 协议契约：[docs/api-contract.md](docs/api-contract.md) · 数据契约：[docs/data-contract.md](docs/data-contract.md)
- 策略任务：[docs/strategy-project.md](docs/strategy-project.md) · 评分标准：[docs/grading-rubric.md](docs/grading-rubric.md)
- 常见问题：[TROUBLESHOOTING.md](TROUBLESHOOTING.md)
</content>
