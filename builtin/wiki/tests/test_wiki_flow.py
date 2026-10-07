from __future__ import annotations

import json

import pytest

from modoor.core.settings import get_settings
from modoor.platform.bootstrap import bootstrap
from modoor.testing import configure_test_db
from builtin.wiki.tools import (
    create_page,
    delete_page,
    get_page,
    list_pages,
    update_page,
    list_projects,
    create_project,
)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="t1",
        MODOOR_CONFIRM_SECRET="secret",
    )
    bootstrap(get_settings())
    yield
    get_settings.cache_clear()


def test_wiki_project_page_crud_and_delete_confirm():
    created_proj = json.loads(create_project(name="Docs", description="d1"))
    assert created_proj["status"] == "ok"
    project_id = created_proj["result"]["project"]["id"]
    home_id = created_proj["result"]["home_page"]["id"]
    assert home_id

    listed_proj = json.loads(list_projects())
    assert listed_proj["result"]["count"] >= 1

    created = json.loads(
        create_page(project_id=project_id, title="Hello", parent_id=home_id)
    )
    assert created["status"] == "ok"
    page_id = created["result"]["id"]
    assert created["result"]["project_id"] == project_id
    assert created["result"]["parent_id"] == home_id

    listed = json.loads(list_pages(project_id=project_id, q="Hello"))
    assert listed["result"]["count"] >= 1

    body = json.dumps(
        [
            {
                "id": "b1",
                "type": "paragraph",
                "props": {
                    "textColor": "default",
                    "backgroundColor": "default",
                    "textAlignment": "left",
                },
                "content": [{"type": "text", "text": "Updated", "styles": {}}],
                "children": [],
            }
        ]
    )
    updated = json.loads(update_page(page_id=page_id, body=body))
    assert "Updated" in updated["result"]["body"]

    got = json.loads(get_page(page_id=page_id))
    assert got["result"]["title"] == "Hello"

    first = json.loads(delete_page(page_id=page_id))
    assert first["status"] == "needs_confirmation"
    token = first["confirmation_token"]

    second = json.loads(delete_page(page_id=page_id, confirmation_token=token))
    assert second["status"] == "ok"
    assert second["result"]["deleted"] is True

    missing = json.loads(get_page(page_id=page_id))
    assert missing["status"] == "error"
    assert missing["error"]["code"] == "not_found"

    home_del = json.loads(delete_page(page_id=home_id))
    assert home_del["status"] == "needs_confirmation"
    denied = json.loads(
        delete_page(page_id=home_id, confirmation_token=home_del["confirmation_token"])
    )
    assert denied["status"] == "error"
