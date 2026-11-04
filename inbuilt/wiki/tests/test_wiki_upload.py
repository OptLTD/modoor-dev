from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from modoor.core.settings import get_settings
from modoor.platform.bootstrap import bootstrap
from modoor.testing import configure_test_db
from modoor.web.app import app
from inbuilt.doc.settings import get_doc_settings


@pytest.fixture()
def client(monkeypatch, tmp_path):
    get_doc_settings.cache_clear()
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="demo",
        MODOOR_CONFIRM_SECRET="secret",
        MODOOR_ADMIN_USERNAME="admin",
        MODOOR_ADMIN_PASSWORD="admin123",
        MODOOR_STORAGE_TYPE="local",
        MODOOR_STORAGE_ROOT=str(tmp_path),
    )
    bootstrap()
    with TestClient(app) as c:
        logged = c.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert logged.status_code == 200, logged.text
        yield c
    get_doc_settings.cache_clear()
    get_settings.cache_clear()


def test_wiki_upload_uses_doc_assets(client: TestClient):
    created = client.post(
        "/api/wiki/projects",
        json={"name": "Uploads", "home_title": "Home"},
    )
    assert created.status_code == 200, created.text
    project = created.json()["project"]
    page = created.json()["home_page"]

    uploaded = client.post(
        "/api/wiki/uploads",
        files={"file": ("photo.png", b"png-bytes", "image/png")},
        data={"page_id": page["id"]},
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    asset = body["asset"]
    assert asset["model"] == "wiki.page"
    assert asset["uukey"] == page["id"]
    assert asset["field"] == "image"
    assert asset["mime_type"] == "image/png"
    assert body["url"] == f"/api/doc/assets/{asset['id']}/content"

    content = client.get(body["url"])
    assert content.status_code == 200
    assert content.content == b"png-bytes"
    assert content.headers["content-type"].startswith("image/png")

    file_upload = client.post(
        "/api/wiki/uploads",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"project_id": project["id"]},
    )
    assert file_upload.status_code == 200, file_upload.text
    assert file_upload.json()["asset"]["field"] == "file"
    assert file_upload.json()["asset"]["model"] == "wiki.project"
