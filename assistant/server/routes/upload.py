"""File upload API endpoint for images and PDFs."""
import logging
import uuid
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

import config

router = APIRouter()
logger = logging.getLogger(__name__)

# Allowed file types
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


class UploadResponse(BaseModel):
    """Upload response model."""
    file_id: str
    filename: str
    content_type: str
    size: int
    path: str
    timestamp: str


class FileInfo(BaseModel):
    """File info model."""
    file_id: str
    filename: str
    content_type: str
    size: int
    created_at: str


def get_file_extension(filename: str) -> str:
    """Get file extension in lowercase."""
    return Path(filename).suffix.lower()


def is_allowed_file(filename: str) -> bool:
    """Check if file type is allowed."""
    return get_file_extension(filename) in ALLOWED_EXTENSIONS


def get_content_type(filename: str) -> str:
    """Get content type from filename."""
    ext = get_file_extension(filename)
    content_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
    }
    return content_types.get(ext, "application/octet-stream")


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """Upload an image or PDF file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    # Generate unique file ID
    file_id = str(uuid.uuid4())
    ext = get_file_extension(file.filename)
    stored_filename = f"{file_id}{ext}"

    # Ensure upload directory exists
    config.FILES_PATH.mkdir(parents=True, exist_ok=True)

    # Save file
    file_path = config.FILES_PATH / stored_filename
    with open(file_path, "wb") as f:
        f.write(content)

    logger.info(f"Uploaded file: {file.filename} -> {stored_filename} ({len(content)} bytes)")

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        content_type=get_content_type(file.filename),
        size=len(content),
        path=str(file_path.relative_to(config.BASE_DIR)),
        timestamp=datetime.now().isoformat()
    )


@router.get("/file/{file_id}")
async def get_file(file_id: str):
    """Get file info by ID."""
    # Find file with this ID
    files = list(config.FILES_PATH.glob(f"{file_id}.*"))
    if not files:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = files[0]
    stat = file_path.stat()

    return FileInfo(
        file_id=file_id,
        filename=file_path.name,
        content_type=get_content_type(file_path.name),
        size=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_ctime).isoformat()
    )


@router.get("/file/{file_id}/content")
async def get_file_content(file_id: str):
    """Get file content as base64 for sending to AI."""
    files = list(config.FILES_PATH.glob(f"{file_id}.*"))
    if not files:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = files[0]
    content_type = get_content_type(file_path.name)

    with open(file_path, "rb") as f:
        content = f.read()

    return {
        "file_id": file_id,
        "content_type": content_type,
        "data": base64.b64encode(content).decode("utf-8")
    }


@router.get("/files")
async def list_files():
    """List all uploaded files."""
    if not config.FILES_PATH.exists():
        return {"files": []}

    files = []
    for file_path in config.FILES_PATH.iterdir():
        if file_path.is_file():
            stat = file_path.stat()
            file_id = file_path.stem
            files.append(FileInfo(
                file_id=file_id,
                filename=file_path.name,
                content_type=get_content_type(file_path.name),
                size=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_ctime).isoformat()
            ))

    return {"files": files}
