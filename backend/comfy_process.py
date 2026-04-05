"""Manages the ComfyUI subprocess lifecycle."""
import asyncio
import sys
from collections import deque
from pathlib import Path
from typing import Optional

import httpx

_process: Optional[asyncio.subprocess.Process] = None
_log_deque: deque = deque(maxlen=500)


def _get_python(comfyui_path: Path) -> str:
    """Resolve the correct Python executable for this ComfyUI install."""
    # For ComfyUI Desktop the venv lives in <user_home>/Documents/ComfyUI/.venv.
    # Path.home() may return a different drive (e.g. C:) from where the user
    # data actually lives (e.g. D:), so also derive the user home from the
    # comfyui_path itself: AppData is always <user_home>/AppData/...
    user_homes: list[Path] = [Path.home()]
    try:
        # Walk up from comfyui_path to find the folder that contains "AppData"
        for parent in comfyui_path.parents:
            if (parent / "AppData").exists():
                user_homes.insert(0, parent)  # prefer this one
                break
    except Exception:
        pass

    candidates: list[Path] = [
        # Portable Windows bundle (classic): python_embeded one level up
        comfyui_path.parent / "python_embeded" / "python.exe",
        # ComfyUI Desktop app alternative layout: resources/python/
        comfyui_path.parent / "python" / "python.exe",
        # Two levels up (Programs/ComfyUI/python_embeded)
        comfyui_path.parent.parent / "python_embeded" / "python.exe",
        comfyui_path.parent.parent / "python" / "python.exe",
        # Local venv inside the ComfyUI directory
        comfyui_path / "venv" / "Scripts" / "python.exe",
    ]

    # Add Desktop venv candidates for every user home we found
    for home in user_homes:
        candidates.append(home / "Documents" / "ComfyUI" / ".venv" / "Scripts" / "python.exe")

    for p in candidates:
        if p.exists():
            return str(p)

    # Fall back to whichever Python is running this app
    return sys.executable


async def _read_stdout(proc: asyncio.subprocess.Process) -> None:
    """Background task: stream ComfyUI stdout into the log deque."""
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        _log_deque.append(line.decode("utf-8", errors="replace").rstrip())


async def is_already_running(port: int) -> bool:
    """Return True if a ComfyUI instance is already responding on *port*."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"http://localhost:{port}/system_stats", timeout=2.0
            )
            return r.status_code == 200
    except Exception:
        return False


async def _run_pip(python_exe: str, *args: str) -> int:
    """Run a pip command and stream output to the log deque. Returns exit code."""
    cmd = [python_exe, "-m", "pip"] + list(args) + ["--disable-pip-version-check"]
    _log_deque.append(f"[pip] {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    async for line in proc.stdout:
        _log_deque.append(line.decode("utf-8", errors="replace").rstrip())
    await proc.wait()
    return proc.returncode


async def _install_requirements(python_exe: str, comfyui_path: Path) -> None:
    """Ensure ComfyUI's dependencies are installed using its own Python."""
    req_file = comfyui_path / "requirements.txt"
    if not req_file.exists():
        _log_deque.append("[launcher] No requirements.txt found — skipping.")
        return

    _log_deque.append("[launcher] Installing ComfyUI dependencies…")

    # Install from requirements.txt
    rc = await _run_pip(python_exe, "install", "-r", str(req_file))
    if rc != 0:
        _log_deque.append(f"[launcher] requirements.txt install exited with code {rc} — retrying with --upgrade")
        await _run_pip(python_exe, "install", "-r", str(req_file), "--upgrade")

    # comfyui-frontend-package is often missing even after requirements install;
    # install it explicitly to be safe.
    rc2 = await _run_pip(python_exe, "install", "comfyui-frontend-package")
    if rc2 == 0:
        _log_deque.append("[launcher] comfyui-frontend-package installed OK.")
    else:
        _log_deque.append(f"[launcher] WARNING: comfyui-frontend-package install failed (code {rc2}).")

    _log_deque.append("[launcher] Dependencies ready.")


async def start(settings) -> None:
    """Launch ComfyUI as a background subprocess (no-op if already running)."""
    global _process

    if await is_already_running(settings.comfyui_port):
        _log_deque.append("[launcher] ComfyUI already running — skipping start.")
        return

    comfyui_path = Path(settings.comfyui_path)
    python_exe = _get_python(comfyui_path)

    _log_deque.append(f"[launcher] Using Python: {python_exe}")

    # Ensure ComfyUI's own dependencies are installed before launching
    await _install_requirements(python_exe, comfyui_path)

    cmd = [
        python_exe,
        "main.py",
        "--port", str(settings.comfyui_port),
        "--disable-auto-launch",
    ] + list(settings.extra_comfyui_args)

    _log_deque.append(f"[launcher] Running: {' '.join(cmd)}")

    _process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(comfyui_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    asyncio.create_task(_read_stdout(_process))


async def health_check(port: int, timeout: int = 180) -> bool:
    """Poll /system_stats until ComfyUI responds or *timeout* seconds elapse."""
    deadline = asyncio.get_event_loop().time() + timeout
    delay = 1.0
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await client.get(
                    f"http://localhost:{port}/system_stats", timeout=3.0
                )
                if r.status_code == 200:
                    _log_deque.append("[launcher] ComfyUI is ready.")
                    return True
            except Exception:
                pass
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 8.0)

    _log_deque.append("[launcher] Health check timed out — ComfyUI did not start.")
    return False


async def stop() -> None:
    """Gracefully terminate the managed ComfyUI subprocess."""
    global _process
    if _process and _process.returncode is None:
        _log_deque.append("[launcher] Stopping ComfyUI...")
        _process.terminate()
        try:
            await asyncio.wait_for(_process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            _process.kill()
        _process = None


def is_running() -> bool:
    return _process is not None and _process.returncode is None


def get_logs(n: int = 30) -> list[str]:
    return list(_log_deque)[-n:]
