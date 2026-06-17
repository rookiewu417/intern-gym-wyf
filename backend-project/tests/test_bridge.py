import asyncio

from market_state_engine.bridge import ThreadAsyncBridge


class FakeEngine:
    def __init__(self):
        self.calls = []
    def apply(self, period, symbol, payload):
        self.calls.append((period, symbol, payload))
        return {"type": "delta", "symbol": symbol, "seq": len(self.calls)}


def test_sink_routes_through_loop_and_enqueues():
    async def main():
        engine = FakeEngine()
        bridge = ThreadAsyncBridge(engine)
        bridge.bind(asyncio.get_running_loop())
        sink = bridge.make_sink()
        sink("1m", "02723.HK", {"x": 1})          # 模拟 daemon 线程调用（此处同线程，但走 call_soon_threadsafe）
        await asyncio.sleep(0.05)                  # 让 call_soon 回调跑
        frame = await asyncio.wait_for(bridge.aqueue.get(), timeout=1.0)
        assert frame["symbol"] == "02723.HK" and frame["seq"] == 1
        assert engine.calls == [("1m", "02723.HK", {"x": 1})]
    asyncio.run(main())


def test_sink_noop_when_loop_unbound_or_closed():
    engine = FakeEngine()
    bridge = ThreadAsyncBridge(engine)
    sink = bridge.make_sink()                      # 未 bind，loop is None
    sink("1m", "X", {})                            # 不抛
    assert engine.calls == []
