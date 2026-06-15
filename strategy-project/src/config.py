from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    threshold: float = 0.05                 # 首日动量信号阈值
    holding_days: int = 3                   # 持仓窗口 K
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.20
    notional_per_trade: float = 100_000.0
    grey_filter_field: str = "grey_change_pct"   # 主过滤字段；或 "premium_to_ipo_price"
    grey_premium_min: float = 0.0           # 主过滤阈值：filter_field >= 该值
    cost_scale: float = 1.0                 # 成本缩放（敏感性用）


DEFAULT = StrategyConfig()
COST_SENSITIVITY_SCALES = (0.5, 1.0, 2.0)
