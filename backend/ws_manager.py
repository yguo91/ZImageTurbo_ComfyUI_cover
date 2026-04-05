"""WebSocket bridge: relays ComfyUI events to connected browser clients."""
import asyncio
import json
import uuid
from typing import Optional

import websockets
from fastapi import WebSocket, WebSocketDisconnect

# Single client ID shared across all prompt submissions and the WS bridge.
# ComfyUI uses this to route progress events back to the correct connection.
APP_CLIENT_ID: str = str(uuid.uuid4())

_browsers: set[WebSocket] = set()
_bridge_task: Optional[asyncio.Task] = None
_comfyui_port: int = 8188


async def start_bridge(port: int) -> None:
    """Start the background task that bridges ComfyUI → browser."""
    global _bridge_task, _comfyui_port
    _comfyui_port = port
    if _bridge_task and not _bridge_task.done():
        _bridge_task.cancel()
    _bridge_task = asyncio.create_task(_run_bridge())


async def _run_bridge() -> None:
    """Persistently connect to ComfyUI's WebSocket and relay text messages."""
    while True:
        try:
            uri = f"ws://localhost:{_comfyui_port}/ws?clientId={APP_CLIENT_ID}"
            async with websockets.connect(uri, ping_interval=20) as ws:
                async for message in ws:
                    if isinstance(message, str):
                        # Forward JSON event messages to all browser clients
                        await _broadcast(message)
                    # Binary frames are latent preview images — skip them
        except Exception:
            await _broadcast(json.dumps({"type": "comfyui_disconnected"}))
            await asyncio.sleep(2)


async def _broadcast(message: str) -> None:
    """Send a message to every connected browser; remove dead connections."""
    dead: set[WebSocket] = set()
    for browser_ws in list(_browsers):
        try:
            await browser_ws.send_text(message)
        except Exception:
            dead.add(browser_ws)
    _browsers.difference_update(dead)


async def ws_endpoint(websocket: WebSocket) -> None:
    """FastAPI WebSocket handler — registered in main.py."""
    await websocket.accept()
    _browsers.add(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        _browsers.discard(websocket)
