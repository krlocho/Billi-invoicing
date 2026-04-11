import os
import uuid
from pathlib import Path

from src.config import settings


def save_upload(file_content: bytes, original_filename: str, file_type: str) -> str:
    upload_dir = Path(settings.upload_dir) / file_type
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(original_filename).suffix
    stored_name = f"{uuid.uuid4()}{ext}"
    stored_path = upload_dir / stored_name

    with open(stored_path, "wb") as f:
        f.write(file_content)

    return str(stored_path)
