# Grading Rubric

总分 100。

## Correctness - 40

- 数据能跑通，核心功能完整：10
- broker queue 档位语义正确：10
- effective day / alerts 不串日：10
- WebSocket snapshot/delta/reconnect 正确：10

## Engineering Quality - 25

- 组件/模块边界清晰：8
- 状态管理可解释：7
- 测试覆盖关键坑：7
- 错误处理和空状态合理：3

## UI/UX 或 API Design - 20

前端：

- 桌面/移动端布局稳定：8
- K 线、成交量、队列、alerts 信息层级清楚：8
- 数据时间和状态展示清楚：4

后端：

- 状态机设计简洁：8
- payload contract 稳定：8
- freshness/source evidence 清楚：4

## Communication - 15

- PR 描述清楚：5
- 能解释 tradeoff：5
- 能说明已知限制和下一步：5

## Red Flags

- 把 broker queue 当增量累加。
- 10/100/1000 档重新编号。
- 混入旧日期大额交易。
- 页面必须手动刷新才更新。
- 大量临时 patch，没有测试说明。

