import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings


def ensure_upload_directory_exists() -> Path:
    upload_directory = Path(settings.upload_dir)
    upload_directory.mkdir(parents=True, exist_ok=True)
    return upload_directory


def build_stored_file_name(original_file_name: str) -> str:
    file_extension = Path(original_file_name).suffix.lower()
    return f"{uuid.uuid4()}{file_extension}"


async def save_upload_file(upload_file: UploadFile) -> tuple[str, str, int, str]:
    upload_directory = ensure_upload_directory_exists()
    stored_file_name = build_stored_file_name(upload_file.filename)
    file_path = upload_directory / stored_file_name

    content = await upload_file.read()

    with open(file_path, "wb") as output_file:
        output_file.write(content)

    file_hash_sha256 = hashlib.sha256(content).hexdigest()
    file_size_bytes = len(content)

    return str(file_path), stored_file_name, file_size_bytes, file_hash_sha256