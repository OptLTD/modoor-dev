"""Blob storage backends for doc assets.

``MODOOR_STORAGE_TYPE`` selects ``local`` or ``aliyun-oss``. Bytes are always
written under ``MODOOR_STORAGE_ROOT`` first so parsing can stay local. With
``aliyun-oss`` that directory is only a cache: after a successful upload it
may be deleted, and reads fall back to the bucket.
``s3`` / ``minio`` are not wired.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from email.utils import formatdate
from pathlib import Path
from typing import Protocol
from urllib.parse import quote
from xml.etree import ElementTree

import httpx

from modoor.core.errors import AppError
from builtin.doc.settings import DocSettings, get_doc_settings

log = logging.getLogger("modoor.doc.storage")


class BlobStore(Protocol):
    backend: str

    def put(self, name: str, data: bytes, *, content_type: str = "") -> None: ...

    def get(self, name: str) -> bytes: ...

    def delete(self, name: str) -> None: ...

    def exists(self, name: str) -> bool: ...

    def release(self, name: str) -> None:
        """Drop a disposable local copy. The durable object stays."""
        ...


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

    def release(self, name: str) -> None:
        return None


class OssBlobStore:
    """Aliyun OSS via the REST API. Object key is ``prefix + name``."""

    backend = "aliyun-oss"

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        ak_id: str,
        ak_secret: str,
        prefix: str = "doc/",
    ) -> None:
        host = (endpoint or "").strip()
        host = host.removeprefix("https://").removeprefix("http://").strip("/")
        bucket = (bucket or "").strip()
        ak_id = (ak_id or "").strip()
        if not host or not bucket or not ak_id or not ak_secret:
            raise AppError("validation_error", "未配置阿里云 OSS，无法存储文件")
        self.endpoint_host = host
        self.bucket = bucket
        self.ak_id = ak_id
        self.ak_secret = ak_secret
        cleaned = (prefix or "").strip().strip("/")
        self.prefix = f"{cleaned}/" if cleaned else ""

    @classmethod
    def from_settings(cls, settings: DocSettings) -> OssBlobStore:
        return cls(
            endpoint=settings.oss_endpoint,
            bucket=settings.oss_bucket,
            ak_id=settings.oss_ak_id,
            ak_secret=settings.oss_ak_secret,
            prefix=settings.oss_prefix,
        )

    def put(self, name: str, data: bytes, *, content_type: str = "") -> None:
        key = self._object_key(name)
        ctype = (content_type or "").split(";")[0].strip() or "application/octet-stream"
        digest = base64.b64encode(hashlib.md5(data).digest()).decode()
        headers = self._sign("PUT", key, content_type=ctype, content_md5=digest)
        response = self._request("PUT", key, headers=headers, content=data)
        self._raise_for_status(response, "PUT", name)

    def get(self, name: str) -> bytes:
        key = self._object_key(name)
        response = self._request("GET", key, headers=self._sign("GET", key))
        if response.status_code == 404:
            raise AppError("not_found", f"blob not found: {name}")
        self._raise_for_status(response, "GET", name)
        return response.content

    def delete(self, name: str) -> None:
        key = self._object_key(name)
        response = self._request("DELETE", key, headers=self._sign("DELETE", key))
        if response.status_code in (200, 204, 404):
            return
        self._raise_for_status(response, "DELETE", name)

    def exists(self, name: str) -> bool:
        key = self._object_key(name)
        response = self._request("HEAD", key, headers=self._sign("HEAD", key))
        if response.status_code == 404:
            return False
        self._raise_for_status(response, "HEAD", name)
        return True

    def _object_key(self, name: str) -> str:
        return f"{self.prefix}{_safe_object_name(name)}"

    def _url(self, key: str) -> str:
        return f"https://{self.bucket}.{self.endpoint_host}/{quote(key, safe='/')}"

    def _sign(
        self,
        method: str,
        key: str,
        *,
        content_type: str = "",
        content_md5: str = "",
    ) -> dict[str, str]:
        date = formatdate(usegmt=True)
        ctype = content_type if method == "PUT" else ""
        md5 = content_md5 if method == "PUT" else ""
        string_to_sign = f"{method}\n{md5}\n{ctype}\n{date}\n/{self.bucket}/{key}"
        digest = hmac.new(self.ak_secret.encode(), string_to_sign.encode(), hashlib.sha1).digest()
        signature = base64.b64encode(digest).decode()
        headers = {
            "Date": date,
            "Authorization": f"OSS {self.ak_id}:{signature}",
        }
        if method == "PUT":
            headers["Content-Type"] = ctype
            headers["Content-MD5"] = md5
        return headers

    def _request(self, method: str, key: str, **kwargs) -> httpx.Response:
        try:
            return httpx.request(method, self._url(key), timeout=60, **kwargs)
        except httpx.HTTPError as exc:
            log.warning("oss %s %s failed: %s", method, key, exc)
            raise AppError("validation_error", "文件存储失败") from exc

    def _raise_for_status(self, response: httpx.Response, method: str, name: str) -> None:
        if response.status_code < 400:
            return
        code = _oss_error_code(response.content)
        log.warning("oss %s %s -> %s %s", method, name, response.status_code, code)
        raise AppError("validation_error", "文件存储失败")


def _safe_object_name(name: str) -> str:
    key = str(name or "").lstrip("/").replace("\\", "/")
    if not key or ".." in key.split("/"):
        raise AppError("validation_error", "invalid storage name")
    return key


def _oss_error_code(body: bytes) -> str:
    if not body:
        return ""
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return ""
    node = root.find("Code")
    return (node.text or "").strip() if node is not None else ""


class CachedOssBlobStore:
    """Write the local cache and OSS. ``release`` deletes only the cache."""

    def __init__(self, local: LocalBlobStore, remote: OssBlobStore) -> None:
        self.local = local
        self.remote = remote
        self.backend = remote.backend

    def put(self, name: str, data: bytes, *, content_type: str = "") -> None:
        self.local.put(name, data, content_type=content_type)
        try:
            self.remote.put(name, data, content_type=content_type)
        except Exception:
            self.local.delete(name)
            raise

    def get(self, name: str) -> bytes:
        if self.local.exists(name):
            return self.local.get(name)
        return self.remote.get(name)

    def delete(self, name: str) -> None:
        self.local.delete(name)
        self.remote.delete(name)

    def exists(self, name: str) -> bool:
        return self.local.exists(name) or self.remote.exists(name)

    def release(self, name: str) -> None:
        self.local.delete(name)


def get_blob_store(settings: DocSettings | None = None) -> BlobStore:
    settings = settings or get_doc_settings()
    kind = str(settings.storage or "local").strip().lower()
    local = LocalBlobStore(Path(settings.local_root))
    if kind in ("", "local"):
        return local
    if kind == "aliyun-oss":
        return CachedOssBlobStore(local, OssBlobStore.from_settings(settings))
    if kind in ("s3", "minio"):
        raise AppError(
            "not_implemented",
            f"doc storage backend '{kind}' is not implemented yet; set MODOOR_STORAGE_TYPE=local",
        )
    raise AppError("validation_error", f"unknown doc storage backend: {kind}")
