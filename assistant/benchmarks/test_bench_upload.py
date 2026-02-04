"""
Benchmarks for File Upload Operations

Critical paths tested:
- File validation
- File writing to disk
- File reading from disk
- File listing
"""

import pytest
import io
import uuid
import base64
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


def create_test_content(size_bytes: int) -> bytes:
    """Create test content of specified size."""
    # Create PNG-like header followed by filler
    header = b"\x89PNG\r\n\x1a\n"
    filler_size = max(0, size_bytes - len(header))
    return header + b"x" * filler_size


class TestFileValidationBenchmarks:
    """Benchmarks for file validation operations."""

    def test_bench_validate_extension(self, benchmark):
        """Benchmark file extension validation."""
        ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"}

        def validate():
            filename = "test_image.png"
            ext = Path(filename).suffix.lower()
            return ext in ALLOWED_EXTENSIONS

        result = benchmark(validate)
        assert result is True

    def test_bench_get_content_type(self, benchmark):
        """Benchmark content type detection."""
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
        }

        def get_type():
            filename = "test_image.png"
            ext = Path(filename).suffix.lower()
            return content_types.get(ext, "application/octet-stream")

        result = benchmark(get_type)
        assert result == "image/png"


class TestFileIOBenchmarks:
    """Benchmarks for file I/O operations."""

    def test_bench_write_1kb(self, benchmark, tmp_path):
        """Benchmark writing a 1KB file."""
        content = create_test_content(1024)
        files_dir = tmp_path / "files"
        files_dir.mkdir(exist_ok=True)

        i = [0]

        def write_file():
            file_path = files_dir / f"file_{i[0]}.png"
            with open(file_path, "wb") as f:
                f.write(content)
            i[0] += 1

        benchmark(write_file)

    def test_bench_write_10kb(self, benchmark, tmp_path):
        """Benchmark writing a 10KB file."""
        content = create_test_content(10 * 1024)
        files_dir = tmp_path / "files"
        files_dir.mkdir(exist_ok=True)

        i = [0]

        def write_file():
            file_path = files_dir / f"file_{i[0]}.png"
            with open(file_path, "wb") as f:
                f.write(content)
            i[0] += 1

        benchmark(write_file)

    def test_bench_write_100kb(self, benchmark, tmp_path):
        """Benchmark writing a 100KB file."""
        content = create_test_content(100 * 1024)
        files_dir = tmp_path / "files"
        files_dir.mkdir(exist_ok=True)

        i = [0]

        def write_file():
            file_path = files_dir / f"file_{i[0]}.png"
            with open(file_path, "wb") as f:
                f.write(content)
            i[0] += 1

        benchmark(write_file)

    def test_bench_write_1mb(self, benchmark, tmp_path):
        """Benchmark writing a 1MB file."""
        content = create_test_content(1024 * 1024)
        files_dir = tmp_path / "files"
        files_dir.mkdir(exist_ok=True)

        i = [0]

        def write_file():
            file_path = files_dir / f"file_{i[0]}.png"
            with open(file_path, "wb") as f:
                f.write(content)
            i[0] += 1

        benchmark(write_file)

    def test_bench_read_10kb(self, benchmark, tmp_path):
        """Benchmark reading a 10KB file."""
        content = create_test_content(10 * 1024)
        file_path = tmp_path / "test_file.png"
        file_path.write_bytes(content)

        def read_file():
            return file_path.read_bytes()

        result = benchmark(read_file)
        assert len(result) == 10 * 1024

    def test_bench_read_and_base64_encode(self, benchmark, tmp_path):
        """Benchmark reading and base64 encoding a file."""
        content = create_test_content(10 * 1024)
        file_path = tmp_path / "test_file.png"
        file_path.write_bytes(content)

        def read_and_encode():
            data = file_path.read_bytes()
            return base64.b64encode(data).decode("utf-8")

        result = benchmark(read_and_encode)
        assert len(result) > 0


class TestFileListingBenchmarks:
    """Benchmarks for file listing operations."""

    def test_bench_list_files_empty(self, benchmark, tmp_path):
        """Benchmark listing an empty directory."""
        files_dir = tmp_path / "files"
        files_dir.mkdir(exist_ok=True)

        def list_files():
            return list(files_dir.iterdir())

        result = benchmark(list_files)
        assert len(result) == 0

    def test_bench_list_files_20(self, benchmark, tmp_path):
        """Benchmark listing 20 files."""
        files_dir = tmp_path / "files"
        files_dir.mkdir(exist_ok=True)

        # Create 20 files
        content = create_test_content(1024)
        for i in range(20):
            (files_dir / f"file_{i}.png").write_bytes(content)

        def list_files():
            return list(files_dir.iterdir())

        result = benchmark(list_files)
        assert len(result) == 20

    def test_bench_list_files_100(self, benchmark, tmp_path):
        """Benchmark listing 100 files."""
        files_dir = tmp_path / "files"
        files_dir.mkdir(exist_ok=True)

        # Create 100 files
        content = create_test_content(1024)
        for i in range(100):
            (files_dir / f"file_{i}.png").write_bytes(content)

        def list_files():
            return list(files_dir.iterdir())

        result = benchmark(list_files)
        assert len(result) == 100

    def test_bench_glob_files(self, benchmark, tmp_path):
        """Benchmark globbing for specific file pattern."""
        files_dir = tmp_path / "files"
        files_dir.mkdir(exist_ok=True)

        # Create mixed files
        for i in range(50):
            (files_dir / f"file_{i}.png").write_bytes(b"x" * 100)
            (files_dir / f"file_{i}.jpg").write_bytes(b"x" * 100)

        file_id = "file_25"

        def glob_file():
            return list(files_dir.glob(f"{file_id}.*"))

        result = benchmark(glob_file)
        assert len(result) == 2


class TestUploadResponseBenchmarks:
    """Benchmarks for upload response construction."""

    def test_bench_construct_response(self, benchmark):
        """Benchmark constructing upload response."""
        from pydantic import BaseModel

        class UploadResponse(BaseModel):
            file_id: str
            filename: str
            content_type: str
            size: int
            path: str
            timestamp: str

        def construct():
            return UploadResponse(
                file_id=str(uuid.uuid4()),
                filename="test_image.png",
                content_type="image/png",
                size=10240,
                path="memory/files/abc123.png",
                timestamp=datetime.now().isoformat()
            )

        result = benchmark(construct)
        assert result.filename == "test_image.png"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--benchmark-only"])
