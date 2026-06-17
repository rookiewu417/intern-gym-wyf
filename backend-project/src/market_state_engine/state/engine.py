from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import pandas as pd

from ..adapters.xtquant_adapter import XtquantAdapter
from ..models import SymbolState, frame
from ..transforms import (
    broker_queue_from_rows, big_trade_alert, compact_name, empty_snapshot,
    filter_current_day, flatten_broker_levels, latest_daily_volume, merge_alert,
    minute_bar, now_iso, touch_freshness, trade_date_from_timestamp, trade_tick,
    update_quote_from_bar, update_quote_from_tick, upsert_bar, upsert_bar_changed,
)


class BaselineStore:
    """唯一的非 SDK 读取：baseline 日量 + 券商名映射 + 标的名。
    因为 xtdata mock 不暴露这些（无 1d 周期、get_instrument_detail 返回 {}），
    与参考实现的 SampleDataStore 同源（sample-data/*.csv）。"""

    def __init__(self, root: str | os.PathLike | None = None):
        self.root = Path(root or os.getenv("XTMOCK_SILVER_ROOT", "sample-data"))
        self.names: dict[str, str] = {}
        self.brokers: dict[str, str] = {}
        self._baseline: dict[str, int] = {}

    def load(self) -> "BaselineStore":
        instruments = pd.read_csv(self.root / "silver_instruments_v1.csv")
        self.names = {
            str(r["symbol"]).upper(): str(r["name"])
            for r in instruments.to_dict("records") if str(r.get("symbol") or "").strip()
        }
        mapping = pd.read_csv(self.root / "silver_broker_mapping_v1.csv")
        self.brokers = {
            str(r["broker_code"]).strip(): compact_name(r.get("participant_name") or r.get("broker_name"))
            for r in mapping.to_dict("records") if str(r.get("broker_code") or "").strip()
        }
        daily = pd.read_csv(self.root / "silver_daily_bars_v1.csv")   # 63 行 OHLCV，front/back baseline，勿混 research-data
        self._baseline = latest_daily_volume(daily)
        return self

    def baseline_for(self, symbol: str) -> int:
        return self._baseline.get(symbol.upper(), 0)


class MarketStateEngine:
    """per-symbol 状态机，与传输层彻底解耦。apply() 在单写者（loop 线程）调用，
    变更 payload、bump per-symbol seq、append delta 环形缓冲，并返回 delta 帧给 gateway 广播。
    effective-day 隔离只在此层。"""

    def __init__(self, symbols: list[str], adapter: XtquantAdapter | None = None, store: BaselineStore | None = None):
        # test_smoke: MarketStateEngine(['02723.HK']) 单参 → 默认构造 store+adapter
        if store is None:
            store = BaselineStore().load()
        if adapter is None:
            adapter = XtquantAdapter(names=store.names)
        self.adapter = adapter
        self.store = store
        self.snapshots: dict[str, SymbolState] = {}   # 名字保留为 snapshots 以兼容 test_smoke
        self._global_lock = threading.Lock()          # 守护 snapshots 字典结构（onboard/offboard）
        for symbol in symbols:
            self._init_state(symbol)

    # ---------- 构造 / effective-day ----------
    def _init_state(self, symbol: str) -> SymbolState:
        name = self.store.names.get(symbol, symbol)
        baseline = self.store.baseline_for(symbol)
        eff = os.getenv("MARKET_EFFECTIVE_DAY", "").strip().replace("-", "")  # 覆盖优先；否则 hydrate 时按 max 日定
        st = SymbolState(symbol=symbol, name=name, baseline_volume=baseline, effective_day=eff)
        self.snapshots[symbol] = st
        return st

    def _effective_day_from_rows(self, rows: list[dict[str, Any]]) -> str:
        configured = os.getenv("MARKET_EFFECTIVE_DAY", "").strip()
        if configured:
            return configured.replace("-", "")
        dates = {d for d in (trade_date_from_timestamp(r.get("bar_ts") or r.get("timestamp") or r.get("time")) for r in rows) if d}
        return max(dates) if dates else ""

    # ---------- hydrate（阻塞 I/O；boot 前调用安全，onboard 经 executor 卸载） ----------
    def hydrate(self) -> None:
        for symbol in list(self.snapshots):
            self.hydrate_symbol(symbol)

    def hydrate_symbol(self, symbol: str) -> None:
        st = self.snapshots[symbol]
        rows = self.adapter.fetch_minute_rows(symbol, count=420)   # 阻塞读，放锁外
        eff = self._effective_day_from_rows(rows)
        queue_payload = self.adapter.fetch_latest_queue_payload(symbol)
        with st.lock:
            st.effective_day = eff
            st.payload = empty_snapshot(symbol, st.name, eff)
            for row in rows:
                bar = minute_bar(row)
                if trade_date_from_timestamp(bar["timestamp"]) != eff:  # hydrate 期日 guard
                    continue
                upsert_bar(st.payload["minute_bars"], bar)
                update_quote_from_bar(st, bar)                          # 注意：这里会把 runtime_state 置 LIVE
            st.payload["alerts"] = filter_current_day(st.payload["alerts"], eff)
            st.payload["minute_bars"] = filter_current_day(st.payload["minute_bars"], eff)
            queue_rows = flatten_broker_levels(queue_payload) if queue_payload else []
            st.payload["broker_queue"] = broker_queue_from_rows(queue_rows, self.store.brokers, effective_day=eff)
            # —— hydrate 收尾：复位 WARM（水合不是 live）+ 写 mock_rows（test_smoke 需要）——
            st.payload["freshness"]["runtime_state"] = "WARM"
            st.payload["freshness"]["effective_day"] = eff
            st.payload["freshness"]["source_dates"] = {}
            st.payload["freshness"]["mock_rows"] = {
                "minute_bars": len(st.payload["minute_bars"]),
                "broker_queue": len(st.payload["broker_queue"]["ask"]) + len(st.payload["broker_queue"]["bid"]),
            }
            st.base_seq = st.seq            # snapshot 现反映 seq=base_seq（seq 本身不回退）
            st.deltas.clear()
            st.seen_tick_ids.clear()
            st.last_queue_ts = ""

    # ---------- live apply（单写者；effective-day 隔离 + 回放变更检测） ----------
    def apply(self, period: str, symbol: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        st = self.snapshots.get(symbol)
        if st is None:
            return None
        with st.lock:
            if period == "1m":
                bar = minute_bar(payload)
                if trade_date_from_timestamp(bar["timestamp"]) != st.effective_day:
                    return None                                    # effective-day 隔离
                if not upsert_bar_changed(st.payload["minute_bars"], bar):
                    return None                                    # 回放 wraparound 同 bar → 不发 delta/不 bump seq
                update_quote_from_bar(st, bar)
                body = {"delta_type": "minute_bar", "minute_bar": bar}
            elif period == "hktransaction":
                tick = trade_tick(payload)
                if tick["tradeDate"] != st.effective_day:
                    return None                                    # effective-day 隔离
                if tick["id"] in st.seen_tick_ids:
                    return None                                    # 重复 tick（wraparound）
                st.seen_tick_ids.add(tick["id"])
                update_quote_from_tick(st, tick)                   # 仅更新 price/updatedAt/tradeDate
                alert = big_trade_alert(st, tick)
                if alert is not None:
                    merge_alert(st.payload["alerts"], alert)       # 按 id 去重
                    touch_freshness(st, alert["timestamp"], "alerts")
                body = {"delta_type": "trade_tick", "tick": tick, "alert": alert}
            elif period == "hkbrokerqueueex":
                qts = payload.get("queue_ts") or payload.get("timestamp") or ""
                if qts and qts == st.last_queue_ts:
                    return None                                    # 同快照重发 → 抑制
                st.last_queue_ts = qts
                queue = broker_queue_from_rows(flatten_broker_levels(payload), self.store.brokers, effective_day=st.effective_day)
                st.payload["broker_queue"] = queue                 # 整快照覆盖，绝不累加
                touch_freshness(st, qts or now_iso(), "broker_queue")
                body = {"delta_type": "broker_queue", "broker_queue": queue}
            else:
                return None
            st.seq += 1
            delta = frame("delta", symbol=symbol, seq=st.seq, payload=body)
            st.deltas.append(delta)
            return delta

    # ---------- 读 ----------
    def snapshot_frame(self, symbol: str) -> dict[str, Any] | None:
        st = self.snapshots.get(symbol)
        if st is None:
            return None
        with st.lock:
            return frame("snapshot", symbol=symbol, seq=max(1, st.seq), payload=st.payload)

    def resume_since(self, symbol: str, last_seq: int) -> tuple[str, list[dict[str, Any]]]:
        st = self.snapshots.get(symbol)
        if st is None:
            return ("snapshot", [])
        with st.lock:
            if last_seq >= st.seq:
                return ("deltas", [])                              # 客户端已最新
            oldest = st.deltas[0]["seq"] if st.deltas else st.seq + 1
            if last_seq >= st.base_seq and last_seq + 1 >= oldest:  # 连续且不落后于快照地板
                return ("deltas", [f for f in st.deltas if f["seq"] > last_seq])
            return ("snapshot", [frame("snapshot", symbol=symbol, seq=max(1, st.seq), payload=st.payload)])

    # ---------- live 订阅 ----------
    def start_live(self, bridge) -> None:
        for symbol in list(self.snapshots):
            self.start_live_symbol(symbol, bridge)

    def start_live_symbol(self, symbol: str, bridge) -> None:
        st = self.snapshots[symbol]
        st.sub_ids = {p: self.adapter.subscribe(symbol, p, bridge.make_sink()) for p in ("1m", "hktransaction", "hkbrokerqueueex")}

    def stop_live(self) -> None:
        for st in self.snapshots.values():
            self.adapter.unsubscribe_symbol_subs(st.sub_ids.values())
            st.sub_ids = {}

    # ---------- 动态 onboard / offboard（拆三步消竞态） ----------
    def prepare_onboard(self, symbol: str) -> bool:
        with self._global_lock:
            if symbol in self.snapshots:
                return False
            self._init_state(symbol)
            return True

    def offboard(self, symbol: str) -> None:
        with self._global_lock:
            st = self.snapshots.pop(symbol, None)
        if st:
            self.adapter.unsubscribe_symbol_subs(st.sub_ids.values())
