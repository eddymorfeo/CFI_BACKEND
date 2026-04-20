from pathlib import Path

from app.core.config import settings


def ensure_export_directory_exists() -> Path:
    export_directory = Path(settings.export_dir)
    export_directory.mkdir(parents=True, exist_ok=True)
    return export_directory