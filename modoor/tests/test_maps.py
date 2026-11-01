"""Map address-search adapters: provider selection and normalized results."""

from __future__ import annotations

import json

import httpx
import pytest

from modoor.core import maps
from modoor.core.errors import AppError


def _settings(
    provider: str = "tianditu", token1: str = "token", token2: str = ""
) -> dict[str, str]:
    return {"provider": provider, "token1": token1, "token2": token2}


class _Resp:
    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("GET", "https://example.test"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict:
        return self._data


class _Img:
    def __init__(
        self,
        content: bytes = b"\x89PNG\r\n\x1a\n",
        content_type: str = "image/png",
        status_code: int = 200,
    ):
        self.content = content
        self.headers = {"content-type": content_type}
        self.status_code = status_code

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "ignore")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("GET", "https://example.test"),
                response=httpx.Response(self.status_code),
            )


def _fake_get(data: dict):
    def get(url, params=None, **kwargs):
        _ = (url, params, kwargs)
        return _Resp(data)

    return get


def test_provider_config_reports_selected_provider():
    cfg = maps.provider_config(_settings("tianditu", "tdt-secret", "server-secret"))

    assert cfg["provider"] == "tianditu"
    assert cfg["configured"] is True
    assert cfg["crs"] == "WGS84"
    assert [p["id"] for p in cfg["providers"]] == list(maps.PROVIDERS)
    assert [p["id"] for p in cfg["providers"] if p["configured"]] == ["tianditu"]
    assert "tdt-secret" not in json.dumps(cfg)
    assert "server-secret" not in json.dumps(cfg)


def test_provider_config_without_token_is_unconfigured():
    cfg = maps.provider_config(_settings("amap", ""))

    assert cfg["provider"] == "amap"
    assert cfg["configured"] is False
    assert cfg["crs"] == "GCJ-02"
    assert not any(p["configured"] for p in cfg["providers"])


def test_search_without_token_fails_clearly():
    with pytest.raises(AppError) as err:
        maps.search_address("连云港站", _settings("tianditu", ""))

    assert err.value.code == "map_not_configured"
    assert "Token" in str(err.value)


def test_provider_override_must_match_global_setting():
    with pytest.raises(AppError) as err:
        maps.search_address(
            "连云港站", _settings("tianditu", "tdt-key"), provider="amap"
        )

    assert err.value.code == "map_not_configured"
    assert "高德地图" in str(err.value)


def test_tianditu_poi_results_are_normalized(monkeypatch):
    monkeypatch.setattr(
        maps.httpx,
        "get",
        _fake_get(
            {
                "pois": [
                    {
                        "name": "连云港站",
                        "address": "江苏省连云港市海州区人民东路",
                        "lonlat": "119.221,34.607",
                    }
                ]
            }
        ),
    )

    payload = maps.search_address("连云港站", _settings(), limit=5)

    assert payload["provider"] == "tianditu"
    assert payload["crs"] == "WGS84"
    hit = payload["results"][0]
    assert hit["name"] == "连云港站"
    assert hit["address"] == "江苏省连云港市海州区人民东路"
    assert hit["lat"] == 34.607
    assert hit["lng"] == 119.221
    assert hit["provider"] == "tianditu"
    assert hit["crs"] == "WGS84"


def test_tianditu_composes_full_address_from_admin_fields(monkeypatch):
    monkeypatch.setattr(
        maps.httpx,
        "get",
        _fake_get(
            {
                "pois": [
                    {
                        "name": "中国石化靖江华发加油站",
                        "province": "江苏省",
                        "city": "泰州市",
                        "county": "靖江市",
                        "address": "建安路4",
                        "lonlat": "120.24875,31.99981",
                    }
                ]
            }
        ),
    )

    hit = maps.search_address("中国石化靖江华发加油站", _settings())["results"][0]

    assert hit["address"] == "江苏省泰州市靖江市建安路4"
    assert hit["lat"] == 31.99981
    assert hit["lng"] == 120.24875


def test_full_address_is_not_duplicated(monkeypatch):
    monkeypatch.setattr(
        maps.httpx,
        "get",
        _fake_get(
            {
                "pois": [
                    {
                        "name": "连云港站",
                        "province": "江苏省",
                        "city": "连云港市",
                        "county": "海州区",
                        "address": "江苏省连云港市海州区人民东路",
                        "lonlat": "119.221,34.607",
                    }
                ]
            }
        ),
    )

    hit = maps.search_address("连云港站", _settings())["results"][0]

    assert hit["address"] == "江苏省连云港市海州区人民东路"


def test_tianditu_reverse_geocode_returns_full_address(monkeypatch):
    def get(url, params=None, **kwargs):
        _ = (params, kwargs)
        if url.endswith("/v2/search"):
            return _Resp(
                {
                    "pois": [
                        {
                            "name": "中国石化靖江华发加油站",
                            "address": "建安路4",
                            "lonlat": "120.24875,31.99981",
                        }
                    ]
                }
            )
        return _Resp(
            {
                "result": {
                    "formatted_address": "江苏省泰州市靖江市靖城街道建安路4"
                }
            }
        )

    monkeypatch.setattr(maps.httpx, "get", get)

    hit = maps.search_address("中国石化靖江华发加油站", _settings())["results"][0]

    assert hit["address"] == "江苏省泰州市靖江市靖城街道建安路4"


def test_tianditu_tries_token2_when_token1_is_browser_only(monkeypatch):
    used: list[str] = []

    def get(url, params=None, **kwargs):
        _ = kwargs
        tk = str((params or {}).get("tk") or "")
        used.append(tk)
        if tk == "browser-key":
            return _Resp({"code": 301012}, status_code=403)
        if url.endswith("/v2/search"):
            return _Resp(
                {
                    "pois": [
                        {
                            "name": "连云港站",
                            "address": "人民东路",
                            "lonlat": "119.221,34.607",
                        }
                    ]
                }
            )
        return _Resp(
            {"result": {"formatted_address": "江苏省连云港市海州区人民东路"}}
        )

    monkeypatch.setattr(maps.httpx, "get", get)

    payload = maps.search_address(
        "连云港站",
        _settings("tianditu", token1="browser-key", token2="server-key"),
    )

    assert payload["results"][0]["address"] == "江苏省连云港市海州区人民东路"
    assert used[0] == "browser-key"
    assert "server-key" in used


def test_static_map_uses_marker_and_returns_image(monkeypatch):
    seen: dict = {}

    def get(url, params=None, **kwargs):
        _ = kwargs
        seen["url"] = url
        seen["params"] = dict(params or {})
        return _Img()

    monkeypatch.setattr(maps.httpx, "get", get)

    content, media = maps.static_map(
        _settings(), lat=31.99981, lng=120.24875, zoom=16, width=640, height=360
    )

    assert content.startswith(b"\x89PNG")
    assert media == "image/png"
    assert seen["url"].endswith("/staticimage")
    assert seen["params"]["center"] == "120.24875,31.99981"
    assert seen["params"]["markers"] == "120.24875,31.99981"
    assert seen["params"]["zoom"] == 16


def test_static_map_tianditu_tries_token2(monkeypatch):
    used: list[str] = []

    def get(url, params=None, **kwargs):
        _ = (url, kwargs)
        tk = str((params or {}).get("tk") or "")
        used.append(tk)
        if tk == "browser-key":
            return _Img(content=b'{"code":301012}', content_type="application/json", status_code=403)
        return _Img()

    monkeypatch.setattr(maps.httpx, "get", get)

    content, _ = maps.static_map(
        _settings("tianditu", token1="browser-key", token2="server-key"),
        lat=31.99981,
        lng=120.24875,
    )

    assert content.startswith(b"\x89PNG")
    assert used[0] == "browser-key"
    assert "server-key" in used


def test_static_map_reports_provider_error(monkeypatch):
    monkeypatch.setattr(
        maps.httpx,
        "get",
        lambda *args, **kwargs: _Img(
            content=b'{"msg":"INVALID_USER_KEY"}',
            content_type="application/json",
        ),
    )

    with pytest.raises(AppError) as err:
        maps.static_map(_settings(), lat=31.99981, lng=120.24875)

    assert err.value.code == "map_static_failed"
    assert "INVALID_USER_KEY" in str(err.value)


def test_join_address_skips_duplicates_and_noise():
    assert (
        maps._join_address("北京市", "北京市", "朝阳区", "建国路1号")
        == "北京市朝阳区建国路1号"
    )
    assert (
        maps._join_address("江苏省", "省直辖县级行政区划", "靖江市", "建安路4")
        == "江苏省靖江市建安路4"
    )


def test_amap_composes_full_address(monkeypatch):
    monkeypatch.setattr(
        maps.httpx,
        "get",
        _fake_get(
            {
                "status": "1",
                "pois": [
                    {
                        "id": "B001",
                        "name": "中国石化靖江华发加油站",
                        "pname": "江苏省",
                        "cityname": "泰州市",
                        "adname": "靖江市",
                        "address": "建安路4",
                        "location": "120.24875,31.99981",
                    }
                ],
            }
        ),
    )

    hit = maps.search_address("中国石化靖江华发加油站", _settings("amap", "k"))[
        "results"
    ][0]

    assert hit["address"] == "江苏省泰州市靖江市建安路4"


def test_baidu_composes_full_address(monkeypatch):
    monkeypatch.setattr(
        maps.httpx,
        "get",
        _fake_get(
            {
                "status": 0,
                "results": [
                    {
                        "uid": "u-1",
                        "name": "中国石化靖江华发加油站",
                        "province": "江苏省",
                        "city": "泰州市",
                        "area": "靖江市",
                        "address": "建安路4",
                        "location": {"lat": 31.99981, "lng": 120.24875},
                    }
                ],
            }
        ),
    )

    hit = maps.search_address("中国石化靖江华发加油站", _settings("baidu", "k"))[
        "results"
    ][0]

    assert hit["address"] == "江苏省泰州市靖江市建安路4"


def test_tianditu_falls_back_to_token2(monkeypatch):
    used: list[dict] = []

    def get(url, params=None, **kwargs):
        _ = (url, kwargs)
        used.append(dict(params or {}))
        return _Resp(
            {
                "pois": [
                    {
                        "name": "连云港站",
                        "address": "",
                        "lonlat": "119.221,34.607",
                    }
                ]
            }
        )

    monkeypatch.setattr(maps.httpx, "get", get)

    maps.search_address(
        "连云港站", _settings("tianditu", token1="", token2="server-key")
    )

    assert used[0]["tk"] == "server-key"


def test_tianditu_falls_back_to_geocoder(monkeypatch):
    calls: list[str] = []

    def get(url, params=None, **kwargs):
        _ = (params, kwargs)
        calls.append(url)
        if url.endswith("/v2/search"):
            return _Resp({"pois": []})
        return _Resp(
            {
                "location": {"lon": "119.221", "lat": "34.607"},
                "formatted_address": "江苏省连云港市海州区人民东路",
            }
        )

    monkeypatch.setattr(maps.httpx, "get", get)

    payload = maps.search_address("人民东路", _settings(), limit=5)

    assert calls[-1].endswith("/geocoder")
    assert payload["results"][0]["name"] == "江苏省连云港市海州区人民东路"


def test_amap_results_are_normalized(monkeypatch):
    monkeypatch.setattr(
        maps.httpx,
        "get",
        _fake_get(
            {
                "status": "1",
                "pois": [
                    {
                        "id": "B001",
                        "name": "连云港站",
                        "address": [],
                        "location": "119.221,34.607",
                    }
                ],
            }
        ),
    )

    hit = maps.search_address(
        "连云港站", _settings("amap", "amap-key"), region="连云港"
    )["results"][0]

    assert hit["id"] == "B001"
    assert hit["address"] == ""
    assert hit["label"] == "连云港站"
    assert hit["crs"] == "GCJ-02"


def test_baidu_results_are_normalized(monkeypatch):
    monkeypatch.setattr(
        maps.httpx,
        "get",
        _fake_get(
            {
                "status": 0,
                "results": [
                    {
                        "uid": "u-1",
                        "name": "连云港站",
                        "address": "江苏省连云港市海州区",
                        "location": {"lat": 34.607, "lng": 119.221},
                    }
                ],
            }
        ),
    )

    hit = maps.search_address("连云港站", _settings("baidu", "baidu-key"))["results"][0]

    assert hit["id"] == "u-1"
    assert hit["lat"] == 34.607
    assert hit["crs"] == "BD-09"


def test_google_results_are_normalized(monkeypatch):
    monkeypatch.setattr(
        maps.httpx,
        "get",
        _fake_get(
            {
                "status": "OK",
                "results": [
                    {
                        "place_id": "place-1",
                        "name": "Lianyungang Station",
                        "formatted_address": "Haizhou, Lianyungang, Jiangsu",
                        "geometry": {"location": {"lat": 34.607, "lng": 119.221}},
                    }
                ],
            }
        ),
    )

    hit = maps.search_address(
        "Lianyungang Station", _settings("google", "google-key")
    )["results"][0]

    assert hit["id"] == "place-1"
    assert hit["address"] == "Haizhou, Lianyungang, Jiangsu"
    assert hit["crs"] == "WGS84"


def test_provider_error_is_reported(monkeypatch):
    monkeypatch.setattr(
        maps.httpx,
        "get",
        _fake_get({"status": "0", "info": "INVALID_USER_KEY"}),
    )

    with pytest.raises(AppError) as err:
        maps.search_address("连云港站", _settings("amap", "bad-key"))

    assert err.value.code == "map_search_failed"
    assert "INVALID_USER_KEY" in str(err.value)
