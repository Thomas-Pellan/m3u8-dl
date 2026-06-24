from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolves to backend/.env regardless of where the server is invoked from.
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class AppConfig(BaseSettings):
    output_dir: Path = Path.home() / "Desktop"
    temp_dir: Path = Path.home() / ".m3u8-dl" / "temp"
    keep_segments: bool = False
    capture_mode: str = "auto"
    max_parallel_downloads: int = 2
    preferred_quality: str = "best"
    request_timeout: int = 30
    headless: bool = False
    request_delay_min: float = 1.0
    request_delay_max: float = 3.0

    model_config = SettingsConfigDict(
        env_prefix="M3U8DL_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
    )

    @model_validator(mode="after")
    def _create_dirs(self) -> "AppConfig":
        self.output_dir = self.output_dir.expanduser().resolve()
        self.temp_dir = self.temp_dir.expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        return self