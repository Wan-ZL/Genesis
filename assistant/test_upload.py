"""Test upload functionality."""
import tempfile
import os
from pathlib import Path
from fastapi.testclient import TestClient
import sys

sys.path.insert(0, str(Path(__file__).parent))
from server.main import app

client = TestClient(app)


def test_upload_image():
    """Test uploading an image file."""
    # Create a minimal valid PNG (1x1 transparent pixel)
    png_data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
        0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
        0x54, 0x08, 0xD7, 0x63, 0x00, 0x01, 0x00, 0x00,
        0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
        0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
        0x42, 0x60, 0x82
    ])

    response = client.post(
        "/api/upload",
        files={"file": ("test.png", png_data, "image/png")}
    )

    assert response.status_code == 200, f"Upload failed: {response.text}"
    data = response.json()
    assert "file_id" in data
    assert data["filename"] == "test.png"
    assert data["content_type"] == "image/png"
    print(f"Upload test passed: {data['file_id']}")

    # Test getting file info
    file_id = data["file_id"]
    info_response = client.get(f"/api/file/{file_id}")
    assert info_response.status_code == 200
    print("File info test passed")

    # Test getting file content
    content_response = client.get(f"/api/file/{file_id}/content")
    assert content_response.status_code == 200
    content_data = content_response.json()
    assert "data" in content_data
    print("File content test passed")

    return file_id


def test_upload_invalid_type():
    """Test uploading an invalid file type."""
    response = client.post(
        "/api/upload",
        files={"file": ("test.exe", b"invalid", "application/octet-stream")}
    )
    assert response.status_code == 400
    print("Invalid type rejection test passed")


def test_list_files():
    """Test listing uploaded files."""
    response = client.get("/api/files")
    assert response.status_code == 200
    data = response.json()
    assert "files" in data
    print(f"List files test passed: {len(data['files'])} files")


if __name__ == "__main__":
    print("Testing upload functionality...")
    file_id = test_upload_image()
    test_upload_invalid_type()
    test_list_files()
    print("\nAll upload tests passed!")
