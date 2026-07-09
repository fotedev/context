"""WebSocket endpoint for streaming run progress to the popup.

Each ``/api/run`` response carries a ``run_id``; the popup opens a WS to
``/ws/run/{run_id}`` to receive ``{stage, level, msg, pct}`` events as the
aggregator pipeline (parser → arena → judge) executes server-side.

Lifecycle is logged via the ``gui.server.ws`` logger so ops can grep
for ``ws.connect`` / ``ws.disconnect`` / ``ws.event`` events when
diagnosing connection drops.
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger("gui.server.ws")


class ConnectionManager:
    """Tracks active WS connections keyed by ``run_id``.

    A single run maps to at most one connection. The popup reconnects on
    service-worker wake-ups; run state is keyed server-side by ``run_id``
    so reconnects resume the stream.
    """

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, run_id: str) -> None:
        await websocket.accept()
        self.active_connections[run_id] = websocket
        logger.info("ws.connect run_id=%s active=%d", run_id, len(self.active_connections))

    def disconnect(self, run_id: str) -> None:
        existed = self.active_connections.pop(run_id, None) is not None
        logger.info(
            "ws.disconnect run_id=%s had_connection=%s active=%d",
            run_id,
            existed,
            len(self.active_connections),
        )

    async def send_event(
        self, run_id: str, stage: str, level: str, msg: str, pct: float
    ) -> None:
        """Push a progress event to the popup if it's listening."""
        ws = self.active_connections.get(run_id)
        if ws is None:
            logger.debug(
                "ws.event.dropped run_id=%s stage=%s reason=no_connection",
                run_id,
                stage,
            )
            return
        await ws.send_json(
            {"stage": stage, "level": level, "msg": msg, "pct": pct}
        )
        logger.debug(
            "ws.event run_id=%s stage=%s level=%s pct=%.2f",
            run_id,
            stage,
            level,
            pct,
        )


manager = ConnectionManager()


@router.websocket("/ws/run/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str) -> None:
    """Accept a WS for a run and keep it alive until disconnect.

    The popup sends ``ping`` to keep the connection alive during long runs;
    we reply ``pong``. Progress events arrive via ``manager.send_event``.
    """
    await manager.connect(websocket, run_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(run_id)
        logger.info("ws.client.disconnected run_id=%s", run_id)
