from __future__ import annotations

import asyncio
from typing import Any, Callable


class ThreadAsyncBridge:
    """SDK 在每订阅各自的 daemon 线程触发回调；WS 跑单 asyncio loop。
    用 call_soon_threadsafe 把执行交回 loop 线程（唯一写者），apply 在那里跑、seq 在那里分配 → 无竞态、顺序天然保持。
    apply 产出的 delta 帧推入 asyncio.Queue，由 gateway 排空广播，从而把状态变更与慢客户端的网络扇出解耦。"""

    def __init__(self, engine):
        self.engine = engine
        self.loop: asyncio.AbstractEventLoop | None = None
        self.aqueue: "asyncio.Queue[dict]" | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        # 在 run_server 内、loop 跑起来后调用一次
        self.loop = loop
        self.aqueue = asyncio.Queue()

    def make_sink(self) -> "Callable[[str, str, dict], None]":
        loop = self.loop

        def sink(period: str, symbol: str, payload: dict[str, Any]) -> None:
            # 运行在 SDK daemon 线程：绝不直接碰 asyncio 对象
            if loop is None or loop.is_closed():
                return
            try:
                loop.call_soon_threadsafe(self._on_loop, period, symbol, payload)
            except RuntimeError:
                return    # loop 关闭中的 TOCTOU：吞掉，别让 daemon 线程抛栈

        return sink

    def _on_loop(self, period: str, symbol: str, payload: dict[str, Any]) -> None:
        # 运行在 loop 线程（单写者）
        delta = self.engine.apply(period, symbol, payload)
        if delta is not None and self.aqueue is not None:
            self.aqueue.put_nowait(delta)
