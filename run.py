import sys
from pathlib import Path

# Ensure project root is in sys.path so "backend" package resolves correctly
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from backend.config import load_settings

if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=settings.app_port,
        reload=False,
        log_level="info",
    )
