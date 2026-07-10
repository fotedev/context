"""Unit tests for :mod:`gui.server.ws`.

Covers :class:`ConnectionManager` (add/remove + send_event) and the
``ping``/``pong`` keepalive contract.
"""

from __future__ import annotations

import pytest


class FakeWebSocket:
    """Minimal stub that records ``send_json`` / ``send_text`` calls."""

    def __init__(self) -> None:
        self.accepted = False
        self.sent_json: list[dict] = []
        self.sent_text: list[str] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.sent_json.append(payload)

    async def send_text(self, text: str) -> None:
        self.sent_text.append(text)


class TestConnectionManager:
    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self) -> None:
        from gui.server.ws import ConnectionManager

        mgr = ConnectionManager()
        ws = FakeWebSocket()
        await mgr.connect(ws, "run-1")
        assert ws.accepted
        assert mgr.active_connections.get("run-1") is ws

        mgr.disconnect("run-1")
        assert "run-1" not in mgr.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_unknown_is_safe(self) -> None:
        from gui.server.ws import ConnectionManager

        mgr = ConnectionManager()
        mgr.disconnect("never-existed")  # must not raise

    @pytest.mark.asyncio
    async def test_send_event_to_active_connection(self) -> None:
        from gui.server.ws import ConnectionManager

        mgr = ConnectionManager()
        ws = FakeWebSocket()
        await mgr.connect(ws, "run-1")
        await mgr.send_event("run-1", "init", "info", "starting", 0.1)
        assert ws.sent_json == [
            {"stage": "init", "level": "info", "msg": "starting", "pct": 0.1}
        ]

    @pytest.mark.asyncio
    async def test_send_event_to_unknown_run_id_is_noop(self) -> None:
        from gui.server.ws import ConnectionManager

        mgr = ConnectionManager()
        # No connection registered — should not raise.
        await mgr.send_event("ghost", "init", "info", "x", 0.5)

    @pytest.mark.asyncio
    async def test_disconnect_allows_reconnect(self) -> None:
        from gui.server.ws import ConnectionManager

        mgr = ConnectionManager()
        ws1, ws2 = FakeWebSocket(), FakeWebSocket()
        await mgr.connect(ws1, "run-1")
        mgr.disconnect("run-1")
        await mgr.connect(ws2, "run-1")
        assert mgr.active_connections["run-1"] is ws2


class TestWebsocketEndpoint:
    """Test the /ws/run/{run_id} keepalive ping/pong protocol."""

    @pytest.mark.asyncio
    async def test_ping_replies_with_pong(self) -> None:
        from gui.server.ws import manager, websocket_endpoint

        ws = FakeWebSocket()

        # Fake receive_text that yields "ping" then raises WebSocketDisconnect.
        async def fake_receive_text() -> str:
            return "ping"

        ws.receive_text = fake_receive_text  # type: ignore[assignment]

        from fastapi import WebSocketDisconnect

        # Patch disconnect on the manager so we can clean up after the loop.
        original_disconnect = manager.disconnect

        async def stop_after_one() -> None:
            raise WebSocketDisconnect()

        # The endpoint loops until WebSocketDisconnect. Schedule one raise.
        ws.receive_text = stop_after_one  # type: ignore[assignment]
        await websocket_endpoint(ws, "run-test")

        # After the disconnect, manager should have removed the entry.
        assert "run-test" not in manager.active_connections
        original_disconnect("run-test")  # defensive cleanup
