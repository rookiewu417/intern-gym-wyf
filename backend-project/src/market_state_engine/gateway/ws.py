from __future__ import annotations

import asyncio
import json
from typing import Any

from ..models import frame


class Gateway:
    """WebSocket 协议层（asyncio）。拥有 client 集合，连接握手，命令分发，并发广播。
    从 bridge.aqueue 取现成 delta 帧扇出。不碰 xtquant、不碰业务数学。"""

    def __init__(self, engine, bridge):
        self.engine = engine
        self.bridge = bridge
        self.clients: set[Any] = set()

    async def handle_client(self, ws) -> None:
        self.clients.add(ws)
        try:
            await self._send(ws, frame("hello", payload={"symbols": list(self.engine.snapshots)}))
            await self._send(ws, frame("heartbeat", payload={"ready": True}))
            async for raw in ws:
                try:
                    command = json.loads(raw)
                except Exception:
                    await self._send(ws, frame("error", payload={"code": "bad_json", "message": "invalid JSON"}))
                    continue
                await self._dispatch(ws, command)
        finally:
            self.clients.discard(ws)

    async def _dispatch(self, ws, command: dict[str, Any]) -> None:
        request_id = str(command.get("request_id") or "")
        name = str(command.get("command") or "")
        symbols = [str(s).upper() for s in command.get("symbols", []) if str(s).strip()] or list(self.engine.snapshots)
        await self._send(ws, frame("ack", request_id=request_id, payload={"command": name, "accepted": True}))

        if name in {"snapshot_request", "visible_set", "watchlist_set"}:
            for symbol in symbols:                              # visible_set 仅请求快照，不改 universe、不 re-hydrate
                snap = self.engine.snapshot_frame(symbol)
                if snap is not None:
                    await self._send(ws, snap)
        elif name == "health_request":
            await self._send(ws, frame("heartbeat", request_id=request_id, payload={"ready": True}))
        elif name == "resume_request":
            cursors = command.get("cursors") or {}
            for symbol in symbols:
                last = int(cursors.get(symbol, command.get("last_seq", 0)) or 0)
                _kind, frames = self.engine.resume_since(symbol, last)
                for fr in frames:
                    await self._send(ws, fr)
        elif name == "onboard_request":
            await self._onboard(ws, symbols)
        else:
            await self._send(ws, frame("error", request_id=request_id, payload={"code": "unknown_command", "message": name}))

    async def _onboard(self, ws, symbols: list[str]) -> None:
        loop = asyncio.get_running_loop()
        changed = False
        for symbol in symbols:
            if self.engine.prepare_onboard(symbol):
                # 阻塞 xtdata 读卸到 executor，避免冻结事件循环
                await loop.run_in_executor(None, self.engine.hydrate_symbol, symbol)
                snap = self.engine.snapshot_frame(symbol)
                if snap is not None:
                    await self._send(ws, snap)                 # 请求方先拿到 snapshot，再开 live（消竞态）
                self.engine.start_live_symbol(symbol, self.bridge)
                changed = True
            else:
                snap = self.engine.snapshot_frame(symbol)
                if snap is not None:
                    await self._send(ws, snap)
        if changed:                                            # 通知所有客户端 universe 变化
            await self.broadcast(frame("hello", payload={"symbols": list(self.engine.snapshots)}))

    async def run_broadcast_loop(self) -> None:
        assert self.bridge is not None and self.bridge.aqueue is not None
        while True:
            delta = await self.bridge.aqueue.get()
            await self.broadcast(delta)

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self.clients:
            return
        encoded = json.dumps(message, ensure_ascii=False)
        await asyncio.gather(*(self._safe_send(c, encoded) for c in list(self.clients)), return_exceptions=True)

    async def _safe_send(self, ws, encoded: str) -> None:
        try:
            await ws.send(encoded)
        except Exception:
            self.clients.discard(ws)

    async def _send(self, ws, message: dict[str, Any]) -> None:
        await ws.send(json.dumps(message, ensure_ascii=False))
