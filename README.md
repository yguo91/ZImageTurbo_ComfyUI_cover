# ZImageTurbo

A self-contained browser-based image generation app powered by the [Z-Image Turbo](https://huggingface.co/Comfy-Org/z_image_turbo) diffusion model and ComfyUI.

## Features

- One-click launch — ComfyUI starts silently in the background
- Clean browser UI — no ComfyUI interface exposed to the user
- Real-time progress bar via WebSocket
- Optional Pixel Art Style (LoRA)
- Configurable seed, steps, image size, and filename prefix
- Auto-randomize seed after each generation

## Requirements

- Windows 10/11
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) installed (Desktop app or portable)
- Python 3.10+ with pip
- GPU with at least 12GB VRAM recommended

### Required Models

Place these files in your ComfyUI `models/` directory:

| File | Folder | Required |
|---|---|---|
| `z_image_turbo_bf16.safetensors` | `models/diffusion_models/` | Yes |
| `qwen_3_4b.safetensors` | `models/text_encoders/` | Yes |
| `ae.safetensors` | `models/vae/` | Yes |
| `pixel_art_style_z_image_turbo.safetensors` | `models/loras/` | Optional |

Download links are shown in the setup wizard on first run.

## Getting Started

1. Clone or download this repository
2. Double-click `run.bat`
3. On first run, the setup wizard will open in your browser:
   - Select your ComfyUI installation folder
   - Verify all required models are present
   - Click **Start App**
4. On subsequent runs, the app opens directly to the generation UI

## Project Structure

```
ZImageTurbo/
├── run.bat                  # One-click launcher
├── run.py                   # Python entry point
├── requirements.txt         # App dependencies (FastAPI, uvicorn, httpx)
├── backend/
│   ├── main.py              # FastAPI app + lifespan manager
│   ├── config.py            # Settings loader (config.json)
│   ├── comfy_process.py     # ComfyUI subprocess lifecycle
│   ├── comfy_client.py      # HTTP client for ComfyUI REST API
│   ├── workflow.py          # Workflow template + parameter injection
│   ├── image_router.py      # /api/generate, /api/image, /api/status
│   ├── setup_router.py      # /api/setup/* (first-run wizard)
│   └── ws_manager.py        # WebSocket bridge (browser ↔ ComfyUI)
├── frontend/
│   ├── index.html           # Single-page app
│   ├── style.css            # Dark theme
│   └── app.js               # UI logic and WebSocket client
└── reference/
    └── image_z_image_turbo.json   # Original ComfyUI workflow (reference only)
```

## Configuration

`config.json` is auto-generated on first run. You can edit it manually if needed:

```json
{
  "comfyui_path": "C:/path/to/ComfyUI",
  "comfyui_port": 8188,
  "app_port": 7860,
  "extra_comfyui_args": [],
  "output_dir": ""
}
```

To reconfigure (e.g. after moving ComfyUI), delete `config.json` and restart the app.

## Usage Tips

- **Seed** — pin a seed number to reproduce the same image; click 🎲 to randomize
- **Steps** — default 9 is fast; increasing adds quality but the model is optimized for low steps
- **Pixel Art Style** — enables the LoRA; requires the optional model file
- **Filename Prefix** — sets the prefix for saved images in ComfyUI's output folder
- **Image Size** — 1024×1024 is the sweet spot for this model; above 1536 may show quality degradation

## License

This project is a UI wrapper. Model weights and ComfyUI are subject to their own respective licenses.
