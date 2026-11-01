"""Address search adapters — 天地图 / 高德 / 百度 / Google behind one normalized API.

Keys stay on the server. The browser only talks to ``/api/map/*`` so providers
without CORS support (and domain/IP-bound keys) still work.

Every provider returns the same shape::

    {
        "id": "...", "name": "北京大学", "address": "北京市海淀区...",
        "label": "北京大学 北京市海淀区...", "lat": 39.99, "lng": 116.31,
        "provider": "tianditu", "crs": "WGS84",
    }

``crs`` is the provider's native coordinate system: 天地图/Google = WGS84,
高德 = GCJ-02, 百度 = BD-09.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any

import httpx

from modoor.core.errors import AppError

PROVIDERS: tuple[str, ...] = ("tianditu", "amap", "baidu", "google")

PROVIDER_LABELS: dict[str, str] = {
    "tianditu": "天地图",
    "amap": "高德地图",
    "baidu": "百度地图",
    "google": "Google Maps",
}

CRS_BY_PROVIDER: dict[str, str] = {
    "tianditu": "WGS84",
    "amap": "GCJ-02",
    "baidu": "BD-09",
    "google": "WGS84",
}

TIMEOUT_SECONDS = 10.0


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return " ".join(part for part in (_text(v) for v in value) if part)
    if isinstance(value, dict):
        return ""
    return str(value).strip()


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(n):
        return None
    return n


def _lonlat(raw: Any) -> tuple[float, float] | None:
    """Parse provider ``"lng,lat"`` strings."""
    text = _text(raw)
    if "," not in text:
        return None
    left, right = text.split(",", 1)
    lng, lat = _num(left), _num(right)
    if lng is None or lat is None:
        return None
    if not (-180.0 <= lng <= 180.0 and -90.0 <= lat <= 90.0):
        return None
    return lng, lat


# 部分供应商把“市辖区”之类当成区县名，拼地址时直接跳过。
_ADDRESS_NOISE = {"市辖区", "省直辖县级行政区划", "自治区直辖县级行政区划"}


def _overlap(a: str, b: str) -> int:
    """Longest suffix of ``a`` that is also a prefix of ``b``."""
    for n in range(min(len(a), len(b)), 0, -1):
        if a[-n:] == b[:n]:
            return n
    return 0


def _join_address(*parts: Any) -> str:
    """Compose a full address without duplicating shared fragments.

    ``天地图``等供应商把省/市/区县和街道门牌分开返回，例如::

        province="江苏省", city="泰州市", county="靖江市", address="建安路4"

    应得到 ``江苏省泰州市靖江市建安路4``；若 ``address`` 本身已是完整地址，
    则保持原样，避免出现“江苏省江苏省…”。
    """
    out = ""
    for raw in parts:
        part = _text(raw)
        if not part or part in _ADDRESS_NOISE:
            continue
        if not out or out in part:
            out = part
        elif part in out:
            continue
        else:
            out += part[_overlap(out, part) :]
    return out


def _place(
    *,
    provider: str,
    id_: Any,
    name: Any,
    address: Any,
    lat: float,
    lng: float,
) -> dict[str, Any]:
    nm = _text(name)
    addr = _text(address)
    if addr and nm:
        label = addr if nm in addr else f"{nm} {addr}"
    else:
        label = nm or addr
    return {
        "id": _text(id_),
        "name": nm,
        "address": addr,
        "label": label,
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "provider": provider,
        "crs": CRS_BY_PROVIDER[provider],
    }


def _get_json(url: str, params: dict[str, Any], *, provider: str) -> dict[str, Any]:
    try:
        resp = httpx.get(
            url,
            params=params,
            timeout=TIMEOUT_SECONDS,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; Modoor/0.1)",
            },
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise AppError(
            "map_search_failed",
            f"{PROVIDER_LABELS[provider]}返回 HTTP {exc.response.status_code}",
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise AppError(
            "map_search_failed", f"{PROVIDER_LABELS[provider]}请求失败：{exc}"
        ) from exc
    if not isinstance(data, dict):
        raise AppError(
            "map_search_failed", f"{PROVIDER_LABELS[provider]}返回格式不正确"
        )
    return data


def _token(settings: dict[str, str]) -> str:
    # 天地图浏览器 Key 通常也可调 Web 服务接口；服务端 Key 只绑出口 IP，
    # 未备案时反而会 301013，因此地址搜索优先 token1（浏览器 Key）。
    return str(settings.get("token1") or settings.get("token2") or "").strip()


def _configured_provider(settings: dict[str, str]) -> str:
    provider = str(settings.get("provider") or "").strip().lower()
    return provider if provider in PROVIDERS else ""


def provider_config(settings: dict[str, str]) -> dict[str, Any]:
    """Public, key-free map configuration for the browser."""
    chosen = _configured_provider(settings)
    token = _token(settings)
    return {
        "provider": chosen,
        "providers": [
            {
                "id": p,
                "label": PROVIDER_LABELS[p],
                "configured": bool(chosen == p and token),
            }
            for p in PROVIDERS
        ],
        "configured": bool(chosen and token),
        "crs": CRS_BY_PROVIDER.get(chosen, ""),
    }


def _resolve_provider(name: str, settings: dict[str, str]) -> tuple[str, str]:
    chosen = _configured_provider(settings)
    provider = (name or chosen).strip().lower()
    if not provider:
        raise AppError(
            "map_not_configured",
            "尚未配置地址搜索服务，请在「全局设置 → 地图」中选择供应商并填写 Token",
        )
    if provider not in PROVIDERS:
        raise AppError(
            "map_provider_unknown",
            f"未知地图供应商：{provider}（可选 {', '.join(PROVIDERS)}）",
        )
    if provider != chosen:
        current = PROVIDER_LABELS.get(chosen) or "未选择"
        raise AppError(
            "map_not_configured",
            f"{PROVIDER_LABELS[provider]}尚未配置（全局设置当前为 {current}）",
        )
    token = _token(settings)
    if not token:
        raise AppError(
            "map_not_configured",
            f"{PROVIDER_LABELS[provider]}尚未填写 Token",
        )
    return provider, token


def _tianditu_reverse(lat: float, lng: float, key: str) -> str:
    """Full address for a coordinate, including town/road/house number."""
    try:
        data = _get_json(
            "https://api.tianditu.gov.cn/geocoder",
            {
                "postStr": json.dumps(
                    {"lon": lng, "lat": lat, "ver": 1}, ensure_ascii=False
                ),
                "type": "geocode",
                "tk": key,
            },
            provider="tianditu",
        )
    except AppError:
        return ""
    result = data.get("result")
    if not isinstance(result, dict):
        return ""
    return _text(result.get("formatted_address"))


def _tianditu_search(
    query: str, key: str, limit: int, region: str
) -> list[dict[str, Any]]:
    post = {
        "keyWord": query,
        "level": 12,
        "queryType": 1,
        "start": 0,
        "count": limit,
        # queryType=1 要求 mapBound；全国范围，具体结果由关键词排序。
        "mapBound": "73.0,3.0,136.0,54.0",
    }
    try:
        data = _get_json(
            "https://api.tianditu.gov.cn/v2/search",
            {
                "postStr": json.dumps(post, ensure_ascii=False),
                "type": "query",
                "tk": key,
            },
            provider="tianditu",
        )
    except AppError:
        # 有些 Key 只开了地理编码权限，v2 搜索会 403。
        return _tianditu_geocode(query, key)
    if str(data.get("status") or "") == "1":
        return _tianditu_geocode(query, key)
    results: list[dict[str, Any]] = []
    for poi in data.get("pois") or []:
        if not isinstance(poi, dict):
            continue
        ll = _lonlat(poi.get("lonlat"))
        if ll is None:
            continue
        lng, lat = ll
        name = _text(poi.get("name"))
        # v2 POI 只给街道门牌（如“建安路4”），省/市/区县/乡镇要靠逆地理编码补齐。
        address = _tianditu_reverse(lat, lng, key) or _join_address(
            poi.get("province"),
            poi.get("city"),
            poi.get("county"),
            poi.get("address"),
        )
        if not (name or address):
            continue
        results.append(
            _place(
                provider="tianditu",
                id_=poi.get("uid") or poi.get("id"),
                name=name,
                address=address,
                lat=lat,
                lng=lng,
            )
        )
        if len(results) >= limit:
            break
    if results:
        return results
    # POI search misses pure addresses often; geocoder still resolves them.
    return _tianditu_geocode(query, key)


def _tianditu_geocode(query: str, key: str) -> list[dict[str, Any]]:
    ds = json.dumps({"keyWord": query}, ensure_ascii=False)
    data = _get_json(
        "https://api.tianditu.gov.cn/geocoder",
        {"ds": ds, "tk": key},
        provider="tianditu",
    )
    loc = data.get("location")
    if not isinstance(loc, dict):
        return []
    lat, lng = _num(loc.get("lat")), _num(loc.get("lon"))
    if lat is None or lng is None:
        return []
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return []
    address = _text(data.get("formatted_address")) or query
    return [
        _place(
            provider="tianditu",
            id_=f"{lat:.6f},{lng:.6f}",
            name=address,
            address=address,
            lat=lat,
            lng=lng,
        )
    ]


def _amap_search(query: str, key: str, limit: int, region: str) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "key": key,
        "keywords": query,
        "offset": limit,
        "page": 1,
        "extensions": "base",
    }
    if region:
        params["city"] = region
        params["citylimit"] = "false"
    data = _get_json("https://restapi.amap.com/v3/place/text", params, provider="amap")
    if str(data.get("status") or "") != "1":
        raise AppError(
            "map_search_failed",
            f"高德地图：{_text(data.get('info')) or '搜索失败'}",
        )
    results: list[dict[str, Any]] = []
    for poi in data.get("pois") or []:
        if not isinstance(poi, dict):
            continue
        ll = _lonlat(poi.get("location"))
        if ll is None:
            continue
        lng, lat = ll
        name = _text(poi.get("name"))
        address = _join_address(
            poi.get("pname"),
            poi.get("cityname"),
            poi.get("adname"),
            poi.get("address"),
        )
        if not (name or address):
            continue
        results.append(
            _place(
                provider="amap",
                id_=poi.get("id"),
                name=name,
                address=address,
                lat=lat,
                lng=lng,
            )
        )
        if len(results) >= limit:
            break
    return results


def _baidu_search(
    query: str, key: str, limit: int, region: str
) -> list[dict[str, Any]]:
    data = _get_json(
        "https://api.map.baidu.com/place/v2/search",
        {
            "query": query,
            "region": region or "全国",
            "output": "json",
            "ak": key,
            "page_size": limit,
            "page_num": 0,
            "scope": 2,
        },
        provider="baidu",
    )
    if str(data.get("status")) != "0":
        raise AppError(
            "map_search_failed",
            f"百度地图：{_text(data.get('message')) or '搜索失败'}",
        )
    results: list[dict[str, Any]] = []
    for poi in data.get("results") or []:
        if not isinstance(poi, dict):
            continue
        loc = poi.get("location")
        if not isinstance(loc, dict):
            continue
        lat, lng = _num(loc.get("lat")), _num(loc.get("lng"))
        if lat is None or lng is None:
            continue
        name = _text(poi.get("name"))
        address = _join_address(
            poi.get("province"),
            poi.get("city"),
            poi.get("area"),
            poi.get("address"),
        )
        if not (name or address):
            continue
        results.append(
            _place(
                provider="baidu",
                id_=poi.get("uid"),
                name=name,
                address=address,
                lat=lat,
                lng=lng,
            )
        )
        if len(results) >= limit:
            break
    return results


def _google_search(
    query: str, key: str, limit: int, region: str
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "query": query,
        "key": key,
        "language": "zh-CN",
    }
    if len(region) == 2:
        params["region"] = region.lower()
    data = _get_json(
        "https://maps.googleapis.com/maps/api/place/textsearch/json",
        params,
        provider="google",
    )
    status = _text(data.get("status"))
    if status not in {"OK", "ZERO_RESULTS"}:
        raise AppError(
            "map_search_failed",
            f"Google Maps：{_text(data.get('error_message')) or status or '搜索失败'}",
        )
    results: list[dict[str, Any]] = []
    for poi in data.get("results") or []:
        if not isinstance(poi, dict):
            continue
        loc = (poi.get("geometry") or {}).get("location") or {}
        if not isinstance(loc, dict):
            continue
        lat, lng = _num(loc.get("lat")), _num(loc.get("lng"))
        if lat is None or lng is None:
            continue
        name = _text(poi.get("name"))
        address = _text(poi.get("formatted_address"))
        if not (name or address):
            continue
        results.append(
            _place(
                provider="google",
                id_=poi.get("place_id"),
                name=name,
                address=address,
                lat=lat,
                lng=lng,
            )
        )
        if len(results) >= limit:
            break
    return results


def _static_request(
    provider: str, token: str, lat: float, lng: float, zoom: int, width: int, height: int
) -> tuple[str, dict[str, Any]]:
    if provider == "tianditu":
        return (
            "https://api.tianditu.gov.cn/staticimage",
            {
                "center": f"{lng},{lat}",
                "width": width,
                "height": height,
                "zoom": zoom,
                # cva_c = 中文注记；eva_c 是英文注记。
                "layers": "vec_c,cva_c",
                "markers": f"{lng},{lat}",
                "tk": token,
            },
        )
    if provider == "amap":
        return (
            "https://restapi.amap.com/v3/staticmap",
            {
                "location": f"{lng},{lat}",
                "zoom": min(zoom, 17),
                "size": f"{width}*{height}",
                "markers": f"mid,,A:{lng},{lat}",
                "key": token,
            },
        )
    if provider == "baidu":
        return (
            "https://api.map.baidu.com/staticimage/v2",
            {
                "center": f"{lng},{lat}",
                "width": width,
                "height": height,
                "zoom": zoom,
                "markers": f"{lng},{lat}",
                "markerStyles": "l",
                "ak": token,
            },
        )
    return (
        "https://maps.googleapis.com/maps/api/staticmap",
        {
            "center": f"{lat},{lng}",
            "zoom": zoom,
            # Static Maps caps a free image at 640x640.
            "size": f"{min(width, 640)}x{min(height, 640)}",
            "markers": f"color:red|{lat},{lng}",
            "language": "zh-CN",
            "key": token,
        },
    )


def _fetch_static(
    provider: str, token: str, lat: float, lng: float, zoom: int, width: int, height: int
) -> tuple[bytes, str]:
    url, params = _static_request(provider, token, lat, lng, zoom, width, height)
    try:
        resp = httpx.get(
            url,
            params=params,
            timeout=TIMEOUT_SECONDS,
            headers={
                "Accept": "image/*",
                "User-Agent": "Mozilla/5.0 (compatible; Modoor/0.1)",
            },
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AppError(
            "map_static_failed",
            f"{PROVIDER_LABELS[provider]}静态地图返回 HTTP {exc.response.status_code}",
        ) from exc
    except httpx.HTTPError as exc:
        raise AppError(
            "map_static_failed", f"{PROVIDER_LABELS[provider]}静态地图请求失败：{exc}"
        ) from exc

    media_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    if not media_type.startswith("image/"):
        detail = _text(resp.text)[:160] or "返回格式不正确"
        raise AppError(
            "map_static_failed", f"{PROVIDER_LABELS[provider]}静态地图失败：{detail}"
        )
    return resp.content, media_type


def static_map(
    settings: dict[str, str],
    *,
    lat: float,
    lng: float,
    zoom: int = 15,
    width: int = 640,
    height: int = 360,
) -> tuple[bytes, str]:
    """Render a marker map for ``lat,lng`` through the configured provider.

    Keys stay on the server. 天地图 同样会依次尝试 token1 / token2：浏览器 Key
    不能用于服务端静态图，服务端 Key 往往才是可用的那个。
    """
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        raise AppError("map_static_failed", "坐标超出范围")
    provider, token = _resolve_provider("", settings)
    zoom = max(1, min(int(zoom or 15), 18))
    width = max(64, min(int(width or 640), 1024))
    height = max(64, min(int(height or 360), 1024))
    if provider != "tianditu":
        return _fetch_static(provider, token, lat, lng, zoom, width, height)
    keys = [token]
    alt = str(settings.get("token2") or "").strip()
    if alt and alt not in keys:
        keys.append(alt)
    error: AppError | None = None
    for key in keys:
        try:
            return _fetch_static(provider, key, lat, lng, zoom, width, height)
        except AppError as exc:
            error = exc
    if error is not None:
        raise error
    raise AppError("map_static_failed", "静态地图失败")


def _tianditu_search_any(
    query: str, keys: list[str], limit: int, region: str
) -> list[dict[str, Any]]:
    """Try token1, then token2.

    天地图浏览器 Key 只能从浏览器域名调用，服务端直连会 301012；服务端 Key
    又可能未备案。两个 Key 都配了就依次尝试，避免其中一个失效时整条搜索失败。
    """
    error: AppError | None = None
    for key in keys:
        try:
            return _tianditu_search(query, key, limit, region)
        except AppError as exc:
            error = exc
    if error is not None:
        raise error
    return []


_ADAPTERS: dict[str, Callable[[str, str, int, str], list[dict[str, Any]]]] = {
    "tianditu": _tianditu_search,
    "amap": _amap_search,
    "baidu": _baidu_search,
    "google": _google_search,
}


def search_address(
    query: str,
    settings: dict[str, str],
    *,
    provider: str = "",
    region: str = "",
    limit: int = 8,
) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {
            "query": "",
            "provider": provider or "",
            "label": "",
            "crs": "",
            "results": [],
        }
    resolved, token = _resolve_provider(provider, settings)
    count = max(1, min(int(limit or 8), 20))
    area = (region or "").strip()
    if resolved == "tianditu":
        keys = [token]
        alt = str(settings.get("token2") or "").strip()
        if alt and alt not in keys:
            keys.append(alt)
        results = _tianditu_search_any(q, keys, count, area)
    else:
        results = _ADAPTERS[resolved](q, token, count, area)
    return {
        "query": q,
        "provider": resolved,
        "label": PROVIDER_LABELS[resolved],
        "crs": CRS_BY_PROVIDER[resolved],
        "results": results,
    }
