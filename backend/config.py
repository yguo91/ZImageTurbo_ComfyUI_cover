import json
from pathlib import Path
from pydantic import BaseModel

CONFIG_FILE = Path(__file__).parent.parent / "config.json"


class Settings(BaseModel):
    comfyui_path: str = ""
    comfyui_port: int = 8188
    app_port: int = 7860
    extra_comfyui_args: list[str] = []
    output_dir: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.comfyui_path) and Path(self.comfyui_path).exists()

    @property
    def effective_output_dir(self) -> Path:
        if self.output_dir:
            return Path(self.output_dir)
        return Path(self.comfyui_path) / "output"


def load_settings() -> Settings:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return Settings(**data)
        except Exception:
            pass
    return Settings()


def save_settings(settings: Settings) -> None:
    CONFIG_FILE.write_text(
        json.dumps(settings.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
