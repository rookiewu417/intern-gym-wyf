from __future__ import annotations

from typing import Any, Callable, Iterable

from xtquant import xtdata

from ..transforms import ms_to_hk_iso

LIVE_PERIODS = ("1m", "hktransaction", "hkbrokerqueueex")
# hkbrokerqueueex 缺省 field_list 会被裁成 ['time','askbrokerqueues','bidbrokerqueues']，丢掉 queue_ts。
# 显式带上 queue_ts/timestamp 才能保住 sourceDate / historical / fallback。
QUEUE_FIELDS = ["time", "queue_ts", "timestamp", "askbrokerqueues", "bidbrokerqueues"]


class XtquantAdapter:
    """唯一接触 xtquant 的层。hydrate 用 get_market_data_ex（count 有效），live 用 subscribe_quote。
    不知道 WS 帧、不知道 seq。回调极薄：只解包 {symbol:[payload]} 并交给注入的 sink。"""

    def __init__(self, *, names: dict[str, str]):
        self._names = names
        self._subs: dict[int, tuple[str, str]] = {}   # sub_id -> (symbol, period)

    # ---------- hydrate（历史，count 受限；subscribe 不能回填） ----------
    def fetch_minute_rows(self, symbol: str, *, count: int = 420) -> list[dict[str, Any]]:
        data = xtdata.get_market_data_ex([], [symbol], period="1m", count=count)
        df = data.get(symbol)
        if df is None or len(df) == 0:
            return []
        rows: list[dict[str, Any]] = []
        for record in df.to_dict("records"):
            if not record.get("bar_ts") and record.get("time") is not None:
                record["bar_ts"] = ms_to_hk_iso(record["time"])   # 修复：SDK 1m 只有 epoch 整数(本 lab 为秒)，按量级本地化为 +08:00
            rows.append(record)
        return rows

    def fetch_latest_queue_payload(self, symbol: str) -> dict[str, Any] | None:
        data = xtdata.get_market_data_ex(QUEUE_FIELDS, [symbol], period="hkbrokerqueueex", count=1)
        df = data.get(symbol)
        if df is None or len(df) == 0:
            return None
        return df.iloc[-1].to_dict()

    def fetch_daily_baseline(self, symbol: str) -> int:
        # 先尝试 SDK（本 lab 无 1d 周期 → {} → 0）；BaselineStore 的 CSV 是真正的 baseline 主源。
        try:
            data = xtdata.get_market_data_ex([], [symbol], period="1d", count=1)
        except Exception:
            return 0
        df = data.get(symbol)
        if df is None or len(df) == 0:
            return 0
        try:
            return int(float(df.iloc[-1].get("volume") or 0))
        except (TypeError, ValueError):
            return 0

    # ---------- live ----------
    def subscribe(self, symbol: str, period: str, sink: "Callable[[str, str, dict], None]") -> int:
        assert period in LIVE_PERIODS, f"非法 period: {period}"

        def _cb(message: dict, period: str = period, symbol: str = symbol) -> None:
            # 在 daemon 后台线程上触发：只解包并转交，绝不碰 asyncio 对象
            bucket = message.get(symbol) or next(iter(message.values()), [])
            for payload in bucket:
                if period == "1m" and not payload.get("bar_ts") and payload.get("time") is not None:
                    payload["bar_ts"] = ms_to_hk_iso(payload["time"])
                sink(period, symbol, payload)

        sub_id = xtdata.subscribe_quote(symbol, period=period, callback=_cb)
        self._subs[sub_id] = (symbol, period)
        return sub_id

    def unsubscribe(self, sub_id: int) -> None:
        xtdata.unsubscribe_quote(sub_id)
        self._subs.pop(sub_id, None)

    def unsubscribe_symbol_subs(self, sub_ids: Iterable[int]) -> None:
        for sub_id in list(sub_ids):
            self.unsubscribe(sub_id)
