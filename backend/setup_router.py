"""API routes for first-run setup: path detection, model checks, and launch."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import comfy_process, ws_manager
from .config import Settings, load_settings, save_settings

router = APIRouter()

def _desktop_app_code_path() -> str | None:
    """Return the ComfyUI Desktop app's code path if installed."""
    # Desktop installs the ComfyUI code under AppData/Local/Programs/ComfyUI/resources/ComfyUI
    local = Path.home() / "AppData" / "Local" / "Programs" / "ComfyUI" / "resources" / "ComfyUI"
    return str(local) if (local / "main.py").exists() else None


# Common ComfyUI installation locations on Windows
def _build_common_paths() -> list[str]:
    paths = [
        "C:/ComfyUI",
        "C:/AI/ComfyUI",
        "C:/ComfyUI_windows_portable/ComfyUI",
        "D:/ComfyUI",
        "D:/AI/ComfyUI",
        "D:/ComfyUI_windows_portable/ComfyUI",
        "E:/ComfyUI",
        "E:/ComfyUI_windows_portable/ComfyUI",
        str(Path.home() / "ComfyUI"),
        str(Path.home() / "Desktop/ComfyUI"),
        str(Path.home() / "Downloads/ComfyUI"),
        str(Path.home() / "Documents/ComfyUI"),
    ]
    desktop = _desktop_app_code_path()
    if desktop:
        paths.insert(0, desktop)
    return paths


COMMON_PATHS = _build_common_paths()

REQUIRED_MODELS = [
    {
        "name": "z_image_turbo_bf16.safetensors",
        "directory": "diffusion_models",
        "required": True,
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors",
    },
    {
        "name": "qwen_3_4b.safetensors",
        "directory": "text_encoders",
        "required": True,
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors",
    },
    {
        "name": "ae.safetensors",
        "directory": "vae",
        "required": True,
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors",
    },
    {
        "name": "pixel_art_style_z_image_turbo.safetensors",
        "directory": "loras",
        "required": False,
        "url": "https://huggingface.co/tarn59/pixel_art_style_lora_z_image_turbo/resolve/main/pixel_art_style_z_image_turbo.safetensors",
    },
]


@router.get("/check")
async def check_setup(request: Request):
    """Detect available ComfyUI installations and return current config."""
    settings = request.app.state.settings
    candidates = [p for p in COMMON_PATHS if (Path(p) / "main.py").exists()]
    return {
        "configured": settings.is_configured,
        "current_path": settings.comfyui_path,
        "candidates": candidates,
    }


class ConfigureBody(BaseModel):
    comfyui_path: str


@router.post("/configure")
async def configure(body: ConfigureBody, request: Request):
    """Validate a ComfyUI path and persist it to config.json."""
    path = Path(body.comfyui_path).resolve()
    if not path.exists():
        raise HTTPException(status_code=400, detail="Path does not exist.")
    if not (path / "main.py").exists():
        raise HTTPException(
            status_code=400,
            detail="ComfyUI main.py not found at this path. Make sure you selected the ComfyUI root folder.",
        )

    current = load_settings()

    # ComfyUI Desktop keeps its data (models, output) in Documents/ComfyUI,
    # not next to main.py. Auto-detect and set output_dir accordingly.
    output_dir = current.output_dir
    desktop_data = Path.home() / "Documents" / "ComfyUI"
    if "AppData" in str(path) and desktop_data.exists():
        output_dir = str(desktop_data / "output")

    updated = Settings(
        comfyui_path=str(path),
        comfyui_port=current.comfyui_port,
        app_port=current.app_port,
        extra_comfyui_args=current.extra_comfyui_args,
        output_dir=output_dir,
    )
    save_settings(updated)
    request.app.state.settings = updated
    return {"ok": True}


@router.get("/models")
async def check_models(request: Request):
    """Check which required model files are present in the ComfyUI models dir."""
    settings = request.app.state.settings
    if not settings.is_configured:
        raise HTTPException(status_code=400, detail="ComfyUI path not configured.")

    # For ComfyUI Desktop, models live in Documents/ComfyUI/models, not next to main.py
    desktop_data = Path.home() / "Documents" / "ComfyUI"
    if "AppData" in settings.comfyui_path and desktop_data.exists():
        models_dir = desktop_data / "models"
    else:
        models_dir = Path(settings.comfyui_path) / "models"
    result = []
    for m in REQUIRED_MODELS:
        file_path = models_dir / m["directory"] / m["name"]
        result.append({**m, "present": file_path.exists(), "path": str(file_path)})

    return {"models": result}


@router.post("/launch")
async def launch(request: Request):
    """Start ComfyUI and wait for it to be ready (used after setup wizard)."""
    settings = request.app.state.settings
    if not settings.is_configured:
        raise HTTPException(status_code=400, detail="ComfyUI path not configured.")

    await comfy_process.start(settings)
    ready = await comfy_process.health_check(settings.comfyui_port)
    if ready:
        await ws_manager.start_bridge(settings.comfyui_port)

    return {
        "ok": ready,
        "message": "ComfyUI is ready." if ready else "ComfyUI failed to start — check logs.",
    }
