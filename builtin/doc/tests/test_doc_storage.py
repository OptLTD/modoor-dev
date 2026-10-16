from __future__ import annotations

import base64
import hashlib
import hmac

import httpx
import pytest

from builtin.doc.settings import get_doc_settings
from builtin.doc.storage import CachedOssBlobStore, OssBlobStore, get_blob_store
from modoor.core.errors import AppError
from modoor.core.settings import get_settings


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("MODOOR_STORAGE_TYPE", "local")
    monkeypatch.setenv("MODOOR_STORAGE_ROOT", "./storage/doc")
    monkeypatch.setenv("MODOOR_ALIYUN_OSS_ENDPOINT", "")
    monkeypatch.setenv("MODOOR_ALIYUN_OSS_BUCKET", "")
    monkeypatch.setenv("MODOOR_ALIYUN_OSS_AK_ID", "")
    monkeypatch.setenv("MODOOR_ALIYUN_OSS_AK_SECRET", "")
    monkeypatch.setenv("MODOOR_ALIYUN_OSS_PREFIX", "doc/")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_AK_ID", "")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_AK_SECRET", "")
    get_doc_settings.cache_clear()
    get_settings.cache_clear()
    yield
    get_doc_settings.cache_clear()
    get_settings.cache_clear()


def _store() -> OssBlobStore:
    return OssBlobStore(
        endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        bucket="my-bucket",
        ak_id="akid",
        ak_secret="secret",
        prefix="doc/",
    )


def test_oss_requires_config():
    with pytest.raises(AppError, match="未配置阿里云 OSS"):
        OssBlobStore(endpoint="", bucket="", ak_id="", ak_secret="")


def test_oss_does_not_reuse_sms_ak(monkeypatch):
    monkeypatch.setenv("MODOOR_STORAGE_TYPE", "aliyun-oss")
    monkeypatch.setenv("MODOOR_ALIYUN_OSS_ENDPOINT", "oss-cn-hangzhou.aliyuncs.com")
    monkeypatch.setenv("MODOOR_ALIYUN_OSS_BUCKET", "my-bucket")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_AK_ID", "sms-ak")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_AK_SECRET", "sms-secret")
    get_doc_settings.cache_clear()
    get_settings.cache_clear()
    with pytest.raises(AppError, match="未配置阿里云 OSS"):
        get_blob_store()


def test_oss_put_signs_and_uploads(monkeypatch):
    captured: dict = {}

    def _request(method, url, timeout=None, headers=None, content=None):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["content"] = content
        return httpx.Response(200, request=httpx.Request(method, url))

    monkeypatch.setattr("builtin.doc.storage.httpx.request", _request)
    _store().put("1/a.txt", b"hello", content_type="text/plain; charset=utf-8")
    headers = captured["headers"]
    md5 = base64.b64encode(hashlib.md5(b"hello").digest()).decode()
    string_to_sign = f"PUT\n{md5}\ntext/plain\n{headers['Date']}\n/my-bucket/doc/1/a.txt"
    signature = base64.b64encode(
        hmac.new(b"secret", string_to_sign.encode(), hashlib.sha1).digest()
    ).decode()
    assert captured["method"] == "PUT"
    assert captured["url"] == "https://my-bucket.oss-cn-hangzhou.aliyuncs.com/doc/1/a.txt"
    assert captured["content"] == b"hello"
    assert headers["Content-Type"] == "text/plain"
    assert headers["Content-MD5"] == md5
    assert headers["Authorization"] == f"OSS akid:{signature}"


def test_oss_get_delete_exists(monkeypatch):
    seen: list[str] = []

    def _request(method, url, timeout=None, headers=None, content=None):
        seen.append(method)
        body = b"hello" if method == "GET" else b""
        status = 204 if method == "DELETE" else 200
        return httpx.Response(status, content=body, request=httpx.Request(method, url))

    monkeypatch.setattr("builtin.doc.storage.httpx.request", _request)
    store = _store()
    assert store.get("1/a.txt") == b"hello"
    assert store.exists("1/a.txt") is True
    store.delete("1/a.txt")
    assert seen == ["GET", "HEAD", "DELETE"]


def test_oss_missing_object(monkeypatch):
    def _request(method, url, timeout=None, headers=None, content=None):
        xml = b"<Error><Code>NoSuchKey</Code></Error>"
        return httpx.Response(404, content=xml, request=httpx.Request(method, url))

    monkeypatch.setattr("builtin.doc.storage.httpx.request", _request)
    store = _store()
    assert store.exists("1/missing.txt") is False
    with pytest.raises(AppError, match="blob not found"):
        store.get("1/missing.txt")
    store.delete("1/missing.txt")


def test_oss_cache_is_discardable(monkeypatch, tmp_path):
    objects: dict[str, bytes] = {}

    def _request(method, url, timeout=None, headers=None, content=None):
        if method == "PUT":
            objects[url] = content
            return httpx.Response(200, request=httpx.Request(method, url))
        if method == "GET":
            if url not in objects:
                return httpx.Response(404, request=httpx.Request(method, url))
            return httpx.Response(200, content=objects[url], request=httpx.Request(method, url))
        if method == "HEAD":
            status = 200 if url in objects else 404
            return httpx.Response(status, request=httpx.Request(method, url))
        objects.pop(url, None)
        return httpx.Response(204, request=httpx.Request(method, url))

    monkeypatch.setenv("MODOOR_STORAGE_TYPE", "aliyun-oss")
    monkeypatch.setenv("MODOOR_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MODOOR_ALIYUN_OSS_ENDPOINT", "oss-cn-hangzhou.aliyuncs.com")
    monkeypatch.setenv("MODOOR_ALIYUN_OSS_BUCKET", "my-bucket")
    monkeypatch.setenv("MODOOR_ALIYUN_OSS_AK_ID", "akid")
    monkeypatch.setenv("MODOOR_ALIYUN_OSS_AK_SECRET", "secret")
    get_doc_settings.cache_clear()
    get_settings.cache_clear()
    monkeypatch.setattr("builtin.doc.storage.httpx.request", _request)
    store = get_blob_store()
    store.put("1/a.txt", b"hello", content_type="text/plain")
    cached = tmp_path / "1" / "a.txt"
    assert cached.is_file()
    assert store.get("1/a.txt") == b"hello"
    store.release("1/a.txt")
    assert not cached.exists()
    assert store.get("1/a.txt") == b"hello"
    assert store.exists("1/a.txt") is True


def test_oss_rejects_traversal():
    with pytest.raises(AppError, match="invalid storage name"):
        _store().put("../secret.txt", b"x")
