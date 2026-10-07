"""Blob storage backends for doc assets.

Admin selects backend via MODOOR_DOC_STORAGE (local | s3 | minio).
v1 implements local only; s3/minio raise not_implemented until wired.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from modoor.core.errors import AppError
from builtin.doc.settings import DocSettings, get_doc_settings


class BlobStore(Protocol):
    backend: str

    def put(self, name: str, data: bytes, *, content_type: str = "") -> None: ...

    def get(self, name: str) -> bytes: ...

    def delete(self, name: str) -> None: ...

    def exists(self, name: str) -> bool: ...


class LocalBlobStore:
    backend = "local"

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        # Prevent path traversal outside root
        key = str(name or "").lstrip("/").replace("\\", "/")
        if not key or ".." in key.split("/"):
            raise AppError("validation_error", "invalid storage name")
        path = (self.root / key).resolve()
        if not str(path).startswith(str(self.root)):
            raise AppError("validation_error", "invalid storage name")
        return path

    def put(self, name: str, data: bytes, *, content_type: str = "") -> None:  # noqa: ARG002
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, name: str) -> bytes:
        path = self._path(name)
        if not path.is_file():
            raise AppError("not_found", f"blob not found: {name}")
        return path.read_bytes()

    def delete(self, name: str) -> None:
        path = self._path(name)
        if path.is_file():
            path.unlink()
        # best-effort clean empty parents under root
        parent = path.parent
        while parent != self.root and parent.is_dir():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def exists(self, name: str) -> bool:
        return self._path(name).is_file()


def get_blob_store(settings: DocSettings | None = None) -> BlobStore:
    settings = settings or get_doc_settings()
    kind = str(settings.storage or "local").strip().lower()
    if kind == "local":
        return LocalBlobStore(Path(settings.local_root))
    if kind in ("s3", "minio"):
        raise AppError(
            "not_implemented",
            f"doc storage backend '{kind}' is not implemented yet; set MODOOR_DOC_STORAGE=local",
        )
    raise AppError("validation_error", f"unknown doc storage backend: {kind}")
