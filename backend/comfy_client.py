"""Async HTTP client wrapper for the ComfyUI REST API."""
from typing import Any

import httpx


class ComfyUIError(Exception):
    pass


async def post_prompt(port: int, workflow: dict, client_id: str) -> str:
    """Submit a workflow prompt and return the assigned prompt_id."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"http://localhost:{port}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=15.0,
        )
    if r.status_code != 200:
        raise ComfyUIError(f"POST /prompt failed ({r.status_code}): {r.text[:300]}")
    return r.json()["prompt_id"]


async def get_history(port: int, prompt_id: str) -> dict[str, Any]:
    """Fetch execution history for a specific prompt_id."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"http://localhost:{port}/history/{prompt_id}", timeout=10.0
        )
    if r.status_code != 200:
        raise ComfyUIError(f"GET /history failed ({r.status_code})")
    return r.json()


async def get_image_bytes(
    port: int, filename: str, subfolder: str, folder_type: str
) -> bytes:
    """Download a generated image from ComfyUI's /view endpoint."""
    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"http://localhost:{port}/view", params=params, timeout=30.0
        )
    if r.status_code != 200:
        raise ComfyUIError(f"GET /view failed ({r.status_code})")
    return r.content


async def get_system_stats(port: int) -> dict:
    """Return ComfyUI system statistics (used as a health probe)."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"http://localhost:{port}/system_stats", timeout=5.0
        )
    if r.status_code != 200:
        raise ComfyUIError(f"GET /system_stats failed ({r.status_code})")
    return r.json()
