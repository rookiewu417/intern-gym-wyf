from __future__ import annotations

import asyncio
import os

import websockets

# 回出口，保持既有测试 import 不变：
from .models import frame, now_iso, DEFAULT_SYMBOLS, SCHEMA_VERSION, PROTOCOL, SymbolState  # noqa: F401
from .state.engine import MarketStateEngine, BaselineStore
from .adapters.xtquant_adapter import XtquantAdapter
from .bridge import ThreadAsyncBridge
from .gateway.ws import Gateway


def parse_symbols() -> list[str]:
    raw = os.getenv("MARKET_SYMBOLS", ",".join(DEFAULT_SYMBOLS))
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def build_engine(symbols: list[str]) -> tuple[MarketStateEngine, XtquantAdapter, BaselineStore]:
    store = BaselineStore().load()
    adapter = XtquantAdapter(names=store.names)
    engine = MarketStateEngine(symbols, adapter, store)
    return engine, adapter, store


async def run_server(host: str = "0.0.0.0", port: int = 9031) -> None:
    engine, _adapter, _store = build_engine(parse_symbols())
    bridge = ThreadAsyncBridge(engine)
    gateway = Gateway(engine, bridge)

    loop = asyncio.get_running_loop()
    bridge.bind(loop)                 # 捕获 loop（必须在 start_live 前）
    engine.hydrate()                  # boot 期阻塞读 OK（尚未 serve）
    engine.start_live(bridge)         # 启动 15 个 daemon 订阅（5 symbol × 3 period）
    asyncio.create_task(gateway.run_broadcast_loop())

    async with websockets.serve(lambda ws: gateway.handle_client(ws), host, port):
        print(f"candidate backend listening on ws://{host}:{port}/ws", flush=True)
        try:
            await asyncio.Future()
        finally:
            engine.stop_live()        # 协作式停 daemon（unsubscribe 置 stop_event）


def main() -> int:
    asyncio.run(run_server())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
