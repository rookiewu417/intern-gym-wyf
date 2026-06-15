# Market Terminal Internship Lab

这是一个独立的招聘/实习生练习仓库骨架，用来拆分两个小项目：

- `frontend-project`: Market Terminal Lite 前端。
- `backend-project`: Market State Engine Lite 后端。

仓库内置一个 import-compatible `mock xtquant` 和一份裁剪后的样本数据。目标不是复刻完整生产系统，而是让候选人在可控范围内处理我们真实遇到过的问题：实时数据刷新、券商队列语义、effective day 对齐、旧数据恢复、移动端展示。

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
make install
make smoke
make serve
```

启动后：

```text
ws://127.0.0.1:9021/ws
```

Docker 方式：

```bash
docker compose up --build
```

`sample-data` 已随仓库提供。维护者需要重新裁剪数据包时再运行：

```bash
make build-data SILVER_ROOT=/path/to/full/silver-root
```

## What Is Included

```text
mock-xtquant/       xtquant.xtdata 兼容 mock SDK
mock-feed/          浏览器可连接的 WebSocket mock feed
sample-data/        5 支股票的裁剪样本数据
frontend-project/   前端任务说明和骨架
backend-project/    后端任务说明和骨架
docs/               API、数据、评分标准
scripts/            数据裁剪脚本
examples/           mock xtdata smoke 示例
```

默认样本股票：

```text
02723.HK, 02675.HK, 00100.HK, 02513.HK, 06082.HK
```

## Candidate Workflow

1. Fork 或新建分支。
2. 按 `frontend-project/README.md` 或 `backend-project/README.md` 完成一个项目。
3. 提交 PR。
4. PR 需要说明：
   - 实现了什么；
   - 如何运行；
   - 如何验证；
   - 已知限制。

## Boundaries

不要在练习中接入真实 xtquant、Redis、Kafka 或生产 token。这个 lab 的数据源固定为 `mock-xtquant + sample-data`。

评分标准见 [docs/grading-rubric.md](docs/grading-rubric.md)。
