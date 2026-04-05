"""FastAPI application — entry point wired by run.py."""
import asyncio
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import comfy_process, ws_manager
from .config import load_settings
from .image_router import router as image_router
from .setup_router import router as setup_router

BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    settings = load_settings()
    app.state.settings = settings

    if settings.is_configured:
        await comfy_process.start(settings)
        ready = await comfy_process.health_check(settings.comfyui_port)
        if ready:
            await ws_manager.start_bridge(settings.comfyui_port)

    # Open the browser after uvicorn has fully bound the port
    asyncio.get_event_loop().call_later(
        1.5, webbrowser.open, f"http://localhost:{settings.app_port}"
    )

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    await comfy_process.stop()


app = FastAPI(lifespan=lifespan, title="ZImageTurbo")

app.include_router(image_router, prefix="/api")
app.include_router(setup_router, prefix="/api/setup")
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def serve_frontend():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    await ws_manager.ws_endpoint(websocket)
