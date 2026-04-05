"""API routes for image generation, history, image serving, and app status."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from . import comfy_client, comfy_process, ws_manager
from .workflow import GenerationParams, build_api_prompt

router = APIRouter()


@router.post("/generate")
async def generate(params: GenerationParams, request: Request):
    """Build the workflow from user params and submit it to ComfyUI."""
    settings = request.app.state.settings
    workflow = build_api_prompt(params)
    try:
        prompt_id = await comfy_client.post_prompt(
            settings.comfyui_port, workflow, ws_manager.APP_CLIENT_ID
        )
    except comfy_client.ComfyUIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"prompt_id": prompt_id}


@router.get("/history/{prompt_id}")
async def history(prompt_id: str, request: Request):
    """Return execution status and output image list for a completed prompt."""
    settings = request.app.state.settings
    try:
        data = await comfy_client.get_history(settings.comfyui_port, prompt_id)
    except comfy_client.ComfyUIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    entry = data.get(prompt_id, {})
    status_info = entry.get("status", {})
    outputs = entry.get("outputs", {})
    images = outputs.get("9", {}).get("images", [])

    return {
        "status": status_info.get("status_str", "pending"),
        "completed": status_info.get("completed", False),
        "images": images,
    }


@router.get("/image")
async def get_image(
    filename: str,
    request: Request,
    subfolder: str = "",
    type: str = "output",
):
    """Proxy a generated image from ComfyUI's /view endpoint."""
    settings = request.app.state.settings
    try:
        data = await comfy_client.get_image_bytes(
            settings.comfyui_port, filename, subfolder, type
        )
    except comfy_client.ComfyUIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return Response(content=data, media_type="image/png")


@router.get("/status")
async def app_status(request: Request):
    """Return current app readiness, ComfyUI state, and recent log lines."""
    settings = request.app.state.settings

    # Accept either our managed subprocess or an externally started ComfyUI
    running = comfy_process.is_running()
    if not running:
        try:
            await comfy_client.get_system_stats(settings.comfyui_port)
            running = True
        except Exception:
            pass

    return {
        "setup_required": not settings.is_configured,
        "comfyui_running": running,
        "app_ready": running,
        "comfyui_logs": comfy_process.get_logs(20),
    }
