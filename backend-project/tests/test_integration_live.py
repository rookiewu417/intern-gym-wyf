import asyncio
import os

from xtquant import xtdata

from market_state_engine.state.engine import MarketStateEngine, BaselineStore
from market_state_engine.adapters.xtquant_adapter import XtquantAdapter
from market_state_engine.bridge import ThreadAsyncBridge


def test_live_event_flows_to_broadcast_with_monotonic_seq(monkeypatch):
    # 限制每订阅回放事件数，避免无限回放；驱动真实 subscribe → daemon → bridge → apply → aqueue。
    # 关键：回放从最早日(20260601)开始，而默认 effective_day 是最新日(20260609)，会把早期 1m/tick 全部按日隔离丢弃。
    # 故把 effective_day 钉到 20260601，让早期 1m/tick 事件命中有效日，真正走通三类 delta（含 trade_tick）。
    monkeypatch.setenv("XTMOCK_REPLAY_MAX_EVENTS_PER_SUBSCRIPTION", "8")
    monkeypatch.setenv("MARKET_EFFECTIVE_DAY", "20260601")
    # xtdata 持有 module 级 ReplayEngine 单例，config 在构造时由 load_config() 冻结读取一次。
    # 若先前测试已实例化（默认 cap=0 不限），上面的 setenv 不会被 subscribe_quote 看到。
    # 故清空单例：下次 _get_engine() 会在已打补丁的 env 下重建，让 8 事件/订阅上限真正生效
    # （monkeypatch.setattr 会在用例结束自动还原；隔离运行下亦幂等）。
    monkeypatch.setattr(xtdata, "_engine", None, raising=False)

    async def main():
        store = BaselineStore().load()
        engine = MarketStateEngine(["02723.HK"], XtquantAdapter(names=store.names), store)
        engine.hydrate()
        assert engine.snapshots["02723.HK"].effective_day == "20260601"
        bridge = ThreadAsyncBridge(engine)
        bridge.bind(asyncio.get_running_loop())
        engine.start_live(bridge)
        collected = []
        try:
            while len(collected) < 20:                          # 收满 20 或超时即止（总量 ≤ 8×3 - 抑制）
                try:
                    delta = await asyncio.wait_for(bridge.aqueue.get(), timeout=3.0)
                except asyncio.TimeoutError:
                    break
                collected.append(delta)
        finally:
            engine.stop_live()
        assert collected, "应至少收到一个 live delta"
        # 单 symbol → seq 严格单调（apply 在 loop 单写者按序分配并 FIFO 入队）
        seqs = [d["seq"] for d in collected]
        assert seqs == sorted(seqs)
        # 时间戳本地化正确(秒级修复)后，effective_day=20260601 的 tick 不再被丢 → 至少一个 trade_tick delta
        assert any(d["payload"].get("delta_type") == "trade_tick" for d in collected), \
            "effective_day 正确时应有 trade_tick delta；若为 0 说明时间尺度/日隔离回归"
        # broker_queue delta 的 sourceDate 在 live 路径必须被填充（queue_ts 未丢；02723 队列日=20260603）
        bq = [d for d in collected if d["payload"].get("delta_type") == "broker_queue"]
        if bq:
            assert bq[0]["payload"]["broker_queue"]["sourceDate"] == "20260603"

    asyncio.run(main())
