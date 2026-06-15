from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    threshold: float = 0.05                 # 首日动量信号阈值
    holding_days: int = 3                   # 持仓窗口 K
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.20
    trailing_stop_pct: float | None = None  # 设值则用追踪止损替代固定止盈：自移动高点回撤该比例出场
    notional_per_trade: float = 100_000.0
    grey_filter_field: str = "grey_change_pct"   # 主过滤字段；或 "premium_to_ipo_price"
    grey_premium_min: float = 0.0           # 主过滤阈值：filter_field >= 该值
    cost_scale: float = 1.0                 # 成本缩放（敏感性用）


DEFAULT = StrategyConfig()
COST_SENSITIVITY_SCALES = (0.5, 1.0, 2.0)
# 暗盘溢价阈值扫描（仅作用于"有暗盘数据"的标的，是隔离信号区分力的受控实验）
GREY_THRESHOLD_SWEEP = (0.0, 0.1, 0.2, 0.3, 0.5, 1.0)
# 追踪止损 trail% 扫描（呈现收益随 trail 的单调性，避免挑最优门槛）
TRAILING_SWEEP = (0.08, 0.10, 0.15, 0.20)
