#!/usr/bin/env python3
"""Sync fleet.freight (出车排班) → freight.order, then replay dispatch.

Compares the historical 1-vehicle-1-dest assignment against plan_city heuristic
and OR-Tools CVRP on the same day's same-depot orders.

  .venv/bin/python scripts/replay_fleet_dispatch.py
  .venv/bin/python scripts/replay_fleet_dispatch.py --day 2026-09-17 --open
  .venv/bin/python scripts/replay_fleet_dispatch.py --dry-run

This customer: 运费锁在定根需求上，调度只压实际里程。口径见
addon/fleet/OIL_DISPATCH.md（不是 TOS 通论）。

站点坐标优先天地图地理编码（连云港/淮安/盐城），缺结果才按账面行程绕油库摆点。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import uuid
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
OUT_HTML = ROOT / "scripts" / "replay_fleet_dispatch.html"
ORDER_PREFIX = "FL-"

# 苏北油配：齐湖在淮安和平镇，卸点在连云港灌南/灌云/赣榆/东海。
LIANYUNGANG_CENTER = (34.596653, 119.178821)
DEFAULT_CENTER = LIANYUNGANG_CENTER
NAME_COORDS: dict[str, tuple[float, float]] = {
    "江苏齐湖油库": (33.4631, 118.97078),
    "中国石化江苏石油齐湖油库": (33.4631, 118.97078),
    "盛虹石化地付库": (34.55485, 119.60918),
    "江苏上冈油库": (33.53648, 119.997061),
    "中国石化江苏石油上冈油库": (33.53648, 119.997061),
    "江苏新安油库": (34.356301, 118.270421),
    "江苏新海地付库": (35.091865, 119.265217),
    "沿海停车场": (34.09594, 119.35039),
    "和海停车场": (34.599807, 119.147329),
}
GEOCODE_HINTS: dict[str, str] = {
    "江苏齐湖油库": "江苏省淮安市清江浦区和平镇齐湖油库桥",
    "中国石化江苏石油齐湖油库": "江苏省淮安市清江浦区和平镇齐湖油库桥",
    "盛虹石化地付库": "江苏省连云港市连云区徐圩街道江苏虹港石化有限公司",
    "江苏上冈油库": "江苏省盐城市建湖县上冈镇冈西社区2组",
    "中国石化江苏石油上冈油库": "江苏省盐城市建湖县上冈镇冈西社区2组",
    "江苏新安油库": "江苏省徐州市新沂市墨河街道",
    "江苏新海地付库": "江苏省连云港市赣榆区柘汪镇",
    "沿海停车场": "江苏省连云港市灌南县新东北路",
    "和海停车场": "江苏省连云港市海州区临洪西路",
}

# 车队停车场（出收车），不是油库。
PARKING_YARDS: list[dict[str, Any]] = [
    {
        "name": "沿海停车场",
        "company": "沿海危险品运输有限公司",
        "address": "江苏省连云港市灌南县新东北路",
        "lat": 34.09594,
        "lng": 119.35039,
    },
    {
        "name": "和海停车场",
        "company": "连云港和海油品运输有限公司",
        "address": "江苏省连云港市海州区临洪西路",
        "lat": 34.599807,
        "lng": 119.147329,
    },
]


def _ensure_project_env() -> None:
    root_s = str(ROOT)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    os.environ.setdefault("PYTHONPATH", root_s)
    if not VENV_PYTHON.is_file():
        return
    venv_prefix = (ROOT / ".venv").resolve()
    try:
        if Path(sys.prefix).resolve() == venv_prefix:
            return
    except OSError:
        pass
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])


_ensure_project_env()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _payload_set(payload: dict[str, Any], key: str, val: Any) -> None:
    payload[key] = val
    if "." in key:
        group, field = key.split(".", 1)
        blob = dict(payload.get(group) or {}) if isinstance(payload.get(group), dict) else {}
        blob[field] = val
        payload[group] = blob


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, ""):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _day_key(utime: Any) -> str:
    if utime is None:
        return ""
    if isinstance(utime, datetime):
        return utime.date().isoformat()
    s = str(utime)
    return s[:10] if len(s) >= 10 else s


def estimate_freight(km: float, qty: float, toll: float = 0.0) -> float:
    """Same piecewise formula as fleet.freight goods.freight."""
    if km <= 30:
        part = qty * 22.5
    elif km <= 50:
        part = qty * km * 0.697
    elif km <= 100:
        part = qty * km * 0.674
    else:
        rate = 0.641 if toll > 0 else 0.639
        part = qty * km * rate
    return round(part / 1000.0 + (toll * qty) / 1000.0, 2)


def station_code(name: str) -> str:
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:6].upper()
    return f"STAFL{digest}"


def polar_coords(origin: tuple[float, float], km: float, name: str) -> tuple[float, float]:
    lat0, lng0 = origin
    h = hashlib.md5(name.encode("utf-8")).digest()
    ang = int.from_bytes(h[:2], "big") / 65535.0 * 2 * math.pi
    dist = max(1.0, float(km))
    dlat = (dist / 111.0) * math.cos(ang)
    denom = 111.0 * max(0.2, math.cos(math.radians(lat0)))
    dlng = (dist / denom) * math.sin(ang)
    return round(lat0 + dlat, 6), round(lng0 + dlng, 6)


def dest_recorded_km(name: str, trips: list[dict]) -> float:
    miles = [_num((t.get("goods") or {}).get("mileage")) for t in trips if t.get("dest") == name]
    miles = [m for m in miles if m > 1]
    if not miles:
        return 0.0
    miles.sort()
    return miles[len(miles) // 2]


def geocode_keyword(name: str) -> str:
    n = str(name or "").strip()
    if n in GEOCODE_HINTS:
        return GEOCODE_HINTS[n]
    if n.startswith("江苏省") or n.startswith("江苏"):
        return n
    return "江苏省连云港市" + n


def nudge_coords(lat: float, lng: float, name: str, span: float = 0.008) -> tuple[float, float]:
    """Keep 母/子站 from stacking on the same geocoded point."""
    h = hashlib.md5(name.encode("utf-8")).digest()
    dlat = (int.from_bytes(h[:2], "big") / 65535.0 - 0.5) * span
    dlng = (int.from_bytes(h[2:4], "big") / 65535.0 - 0.5) * span
    return round(lat + dlat, 6), round(lng + dlng, 6)


def lookup_or_geocode(
    name: str,
    *,
    tk: str,
    cache: dict[str, tuple[float, float]],
) -> tuple[float, float] | None:
    if name in cache:
        return cache[name]
    if name in NAME_COORDS:
        cache[name] = NAME_COORDS[name]
        return cache[name]
    if not tk:
        return None
    from addon.dispatch import domain as dsp

    hit = dsp._tianditu_geocode(geocode_keyword(name), tk=tk)
    if hit is None:
        return None
    cache[name] = (round(hit[0], 6), round(hit[1], 6))
    time.sleep(0.08)
    return cache[name]


def resolve_coords(
    name: str,
    *,
    origin: tuple[float, float],
    rec_km: float = 0.0,
    tk: str = "",
    cache: dict[str, tuple[float, float]] | None = None,
    jitter: bool = False,
) -> tuple[float, float, str]:
    cache = cache if cache is not None else {}
    hit = lookup_or_geocode(name, tk=tk, cache=cache)
    if hit is not None:
        lat, lng = hit
        source = "geocode"
    elif rec_km > 1:
        lat, lng = polar_coords(origin, rec_km, name)
        source = "polar"
    else:
        lat, lng = polar_coords(origin, 8.0, name)
        source = "polar"
    if jitter:
        lat, lng = nudge_coords(lat, lng, name)
    return lat, lng, source


def load_station_index(session, ctx) -> dict[str, dict]:
    from addon.dispatch import domain as dsp

    out: dict[str, dict] = {}
    for row in dsp._list_docs(session, ctx, dsp.DspStation):
        st = dsp._station_point(dsp._to_values(row))
        name = str(st.get("name") or "").strip()
        if name:
            out[name] = st
        uk = str(st.get("uukey") or "").strip()
        if uk:
            out[uk] = st
    return out


def upsert_station(
    session,
    ctx,
    *,
    name: str,
    kind: str,
    lat: float,
    lng: float,
    existing: dict,
    address: str | None = None,
    remark: str | None = None,
) -> dict:
    from sqlalchemy.orm.attributes import flag_modified

    from addon.dispatch import domain as dsp

    uukey = station_code(name)
    row = dsp._resolve(session, ctx, dsp.DspStation, uukey)
    named = existing.get(name)
    if named and str(named.get("uukey") or "") != uukey and named.get("lat") is not None:
        # Prefer a pre-existing named station (e.g. city demo) over a synthetic one.
        return named
    payload: dict[str, Any] = dict(row.payload) if row is not None else {}
    dsp._payload_set(payload, "basic.name", name)
    dsp._payload_set(payload, "basic.kind", kind)
    dsp._payload_set(payload, "basic.status", "active")
    dsp._payload_set(payload, "basic.address", address or name)
    if remark:
        dsp._payload_set(payload, "basic.remark", remark)
    dsp._payload_set(payload, "loc.lat", lat)
    dsp._payload_set(payload, "loc.lng", lng)
    if row is None:
        row = dsp._insert_doc(
            session,
            ctx,
            dsp.DspStation,
            model="dispatch.station",
            prefix="STA",
            payload=payload,
            uukey=uukey,
        )
    else:
        row.payload = payload
        flag_modified(row, "payload")
        session.flush()
    st = dsp._station_point(dsp._to_values(row))
    existing[name] = st
    existing[str(st.get("uukey") or "")] = st
    return st


def upsert_parking_yards(session, ctx, existing: dict) -> int:
    n = 0
    for yard in PARKING_YARDS:
        upsert_station(
            session,
            ctx,
            name=str(yard["name"]),
            kind="yard",
            lat=float(yard["lat"]),
            lng=float(yard["lng"]),
            existing=existing,
            address=str(yard["address"]),
            remark=str(yard["company"]),
        )
        n += 1
    return n


def upsert_order(session, ctx, trip: dict, depot_st: dict, dest_st: dict, *, force: bool) -> str:
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from addon.freight.domain import TmsOrder

    uukey = f"{ORDER_PREFIX}{trip['uukey']}"
    now = _utcnow()
    volume = _num((trip.get("goods") or {}).get("volume"))
    qty = _num((trip.get("goods") or {}).get("quantity"), volume)
    pallets = 1.0
    payload: dict[str, Any] = {}
    _payload_set(payload, "basic.uukey", uukey)
    _payload_set(payload, "basic.utime", trip.get("utime") or now.isoformat())
    _payload_set(payload, "basic.status", "pending")
    _payload_set(payload, "basic.bizType", trip.get("bizType") or "fuel")
    _payload_set(payload, "basic.customer", trip.get("dest") or dest_st.get("name") or "")
    _payload_set(payload, "basic.fromStation", depot_st.get("uukey") or "")
    _payload_set(payload, "basic.toStation", dest_st.get("uukey") or "")
    _payload_set(payload, "basic.weight", volume)
    _payload_set(payload, "basic.pallets", pallets)
    _payload_set(
        payload,
        "basic.remark",
        f"synced from fleet.freight:{trip['uukey']} volume={volume} qty={qty}",
    )
    _payload_set(payload, "shipper.address", depot_st.get("name") or trip.get("depot") or "")
    _payload_set(payload, "consignee.address", dest_st.get("name") or trip.get("dest") or "")
    _payload_set(payload, "income.quantity", qty)
    _payload_set(payload, "income.tollFee", _num((trip.get("goods") or {}).get("tollFee")))
    _payload_set(payload, "income.mileage", _num((trip.get("goods") or {}).get("mileage")))
    _payload_set(payload, "income.freight", _num((trip.get("goods") or {}).get("freight")))

    row = session.scalar(
        select(TmsOrder).where(TmsOrder.tenant == ctx.tenant, TmsOrder.uukey == uukey)
    )
    if row is None:
        session.add(
            TmsOrder(
                id=str(uuid.uuid4()),
                tenant=ctx.tenant,
                uukey=uukey,
                payload=payload,
                utime=now,
            )
        )
        return "created"
    if not force:
        return "skipped"
    row.payload = payload
    row.utime = now
    flag_modified(row, "payload")
    return "updated"


def historical_plan(depot: dict, trips: list[dict], slots: list[dict]) -> dict[str, Any]:
    from addon.dispatch.domain.solver import waybill_from

    by_trip = {s["id"].split("#", 1)[-1]: s for s in slots}
    waybills = []
    recorded_km = 0.0
    recorded_fee = 0.0
    for t in trips:
        goods = t.get("goods") or {}
        asset = by_trip.get(t["uukey"]) or slots[0]
        demand = {
            "order_id": f"{ORDER_PREFIX}{t['uukey']}",
            "unload_name": t.get("dest_name") or t.get("dest"),
            "customer": t.get("dest"),
            "lat": t["dest_lat"],
            "lng": t["dest_lng"],
            "weight": _num(goods.get("volume")),
            "pallets": 1,
        }
        wb = waybill_from(depot, asset, [demand], solver="historical", reorder=False)
        rec = _num(goods.get("mileage"))
        fee = _num(goods.get("freight"))
        wb["recorded_km"] = rec
        wb["recorded_fee"] = fee
        recorded_km += rec
        recorded_fee += fee
        waybills.append(wb)
    geo_km = round(sum(w["km"] for w in waybills), 1)
    return {
        "name": "历史出车（一车一站）",
        "blurb": "fleet.freight 原排班：一趟一油站。里程按发站→到站直线重算，便于和求解器对比。",
        "waybills": waybills,
        "unassigned": [],
        "km": geo_km,
        "vehicles": len(waybills),
        "recorded_km": round(recorded_km, 1),
        "recorded_fee": round(recorded_fee, 2),
    }


def attach_locked_fee(plan: dict, locked_fee: float, hist_km: float) -> None:
    """Freight is locked to demand; only km delta is the cost lever."""
    plan["locked_fee"] = round(locked_fee, 2)
    plan["km_saved"] = round(hist_km - float(plan.get("km") or 0), 1)


def print_plan(plan: dict, *, max_rows: int = 12) -> None:
    extra = []
    if plan.get("recorded_km") is not None:
        extra.append(f"账面里程 {plan['recorded_km']} km")
    saved = plan.get("km_saved")
    if saved is not None:
        extra.append(f"相对历史 {saved:+.1f} km")
    print(f"\n=== {plan['name']} ===")
    print(plan.get("blurb") or "")
    print(
        f"趟次 {plan['vehicles']}  直线里程 {plan['km']} km  "
        f"未派 {plan.get('unassigned') or '无'}"
        + (("  " + "  ".join(extra)) if extra else "")
    )
    rows = plan.get("waybills") or []
    for w in rows[:max_rows]:
        seq = " → ".join(s["name"] for s in w.get("stops") or [])
        print(
            f"  {w.get('plate')}  {round(w.get('load_kg') or 0, 0):.0f}/"
            f"{round(w.get('capacity_kg') or 0, 0):.0f}L  "
            f"{int(w.get('load_pallets') or 0)}站  {w.get('km')}km"
        )
        print(f"    {seq}")
    if len(rows) > max_rows:
        print(f"    … 其余 {len(rows) - max_rows} 张运单")


def write_html(depot: dict, plans: list[dict], *, title: str, note: str) -> Path:
    colors = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed"]
    payload = {"depot": depot, "plans": plans, "colors": colors, "title": title, "note": note}
    html = _HTML.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
    OUT_HTML.write_text(html, encoding="utf-8")
    return OUT_HTML


_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Fleet → Freight 调度回放</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  :root { --bg:#0f172a; --card:#1e293b; --line:#334155; --txt:#e2e8f0; --muted:#94a3b8; }
  * { box-sizing: border-box; }
  html, body { margin:0; height:100%; font-family: ui-sans-serif, system-ui, "PingFang SC", sans-serif; background:var(--bg); color:var(--txt); }
  .wrap { display:grid; grid-template-rows: auto 1fr; height:100%; }
  header { padding:16px 20px 12px; border-bottom:1px solid var(--line); }
  header h1 { margin:0 0 6px; font-size:18px; }
  header p { margin:0; color:var(--muted); font-size:13px; line-height:1.5; }
  .cols { display:grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); min-height:0; }
  .pane { display:grid; grid-template-rows: auto auto 1fr auto; min-height:0; border-right:1px solid var(--line); }
  .stats { display:flex; gap:8px; padding:12px 14px; flex-wrap:wrap; }
  .stat { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px 10px; }
  .stat b { display:block; font-size:16px; }
  .stat span { color:var(--muted); font-size:11px; }
  .stat.win b { color:#34d399; }
  .legend { padding:0 14px 8px; font-size:12px; color:var(--muted); }
  .map { height: 38vh; min-height: 260px; }
  .list { padding:10px 14px 16px; overflow:auto; font-size:12px; }
  .wb { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px 10px; margin-bottom:6px; }
  .wb h3 { margin:0 0 4px; font-size:12px; display:flex; justify-content:space-between; gap:8px; }
  .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }
  .seq { color:var(--muted); line-height:1.4; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1 id="title">Fleet → Freight 调度回放</h1>
    <p id="note"></p>
  </header>
  <div class="cols" id="cols"></div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const DATA = __PAYLOAD__;
document.getElementById('title').textContent = DATA.title || document.title;
document.getElementById('note').textContent = DATA.note || '';
const winKm = Math.min(...DATA.plans.map(p => p.km || 0).filter(x => x > 0));
const winVeh = Math.min(...DATA.plans.map(p => p.vehicles || 0).filter(x => x > 0));

function renderPane(plan, idx) {
  const el = document.createElement('section');
  el.className = 'pane';
  const saved = plan.km_saved != null ? plan.km_saved : 0;
  const savedTxt = (saved>0?'-':'') + Math.abs(saved) + ' km';
  el.innerHTML = `
    <div class="stats">
      <div class="stat${plan.vehicles===winVeh?' win':''}"><b>${plan.vehicles} 趟</b><span>趟次</span></div>
      <div class="stat${plan.km===winKm?' win':''}"><b>${plan.km} km</b><span>直线里程</span></div>
      <div class="stat${saved>0.5?' win':''}"><b>${savedTxt}</b><span>相对历史</span></div>
      <div class="stat"><b>${(plan.unassigned||[]).length}</b><span>未派</span></div>
    </div>
    <div class="legend">${plan.name} · ${plan.blurb || ''}</div>
    <div class="map" id="map-${idx}"></div>
    <div class="list"></div>`;
  const list = el.querySelector('.list');
  const wbs = plan.waybills || [];
  list.innerHTML = wbs.slice(0, 12).map((w, i) => {
    const color = DATA.colors[i % DATA.colors.length];
    const seq = (w.stops||[]).map(s => s.name).join(' → ');
    return `<div class="wb"><h3><span><i class="dot" style="background:${color}"></i>${w.plate||''}</span>
      <span>${Math.round(w.load_kg||0)}L · ${w.km}km</span></h3>
      <div class="seq">${seq}</div></div>`;
  }).join('') + (wbs.length > 12 ? `<div class="wb">其余 ${wbs.length-12} 张</div>` : '');
  document.getElementById('cols').appendChild(el);
  const map = L.map('map-'+idx);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18 }).addTo(map);
  const bounds = [];
  const depot = DATA.depot;
  L.circleMarker([depot.lat, depot.lng], { radius: 8, color: '#fbbf24', fillColor: '#fbbf24', fillOpacity: 1 }).addTo(map);
  bounds.push([depot.lat, depot.lng]);
  wbs.forEach((w, i) => {
    const color = DATA.colors[i % DATA.colors.length];
    const latlngs = (w.stops||[]).map(s => [s.lat, s.lng]);
    latlngs.forEach(ll => bounds.push(ll));
    if (latlngs.length >= 2) L.polyline(latlngs, { color, weight: 3, opacity: 0.85 }).addTo(map);
    (w.stops||[]).forEach((s, j) => {
      if (j === 0) return;
      L.circleMarker([s.lat, s.lng], { radius: 5, color, fillColor: '#0f172a', fillOpacity: 1, weight: 3 }).addTo(map);
    });
  });
  if (bounds.length) map.fitBounds(bounds, { padding: [20, 20] });
  setTimeout(() => map.invalidateSize(), 80);
}
DATA.plans.forEach((p, i) => renderPane(p, i));
</script>
</body>
</html>
"""


def build_assets(session, ctx, trips: list[dict], *, pack: str) -> list[dict]:
    """One asset slot per historical trip, so vehicles that ran N 趟 that day still have N slots."""
    from sqlalchemy import select

    from addon.fleet.domain.orm import VmsTrailer, VmsVehicle

    ids = {str(t.get("vehicle") or "") for t in trips if t.get("vehicle")}
    vehicles = list(
        session.scalars(
            select(VmsVehicle).where(VmsVehicle.tenant == ctx.tenant, VmsVehicle.uukey.in_(ids))
        ).all()
    ) if ids else []
    by_key = {v.uukey: v for v in vehicles}
    by_plate = {str(v.plate or "").upper(): v for v in vehicles}

    trailer_ids = {str(t.get("trailer") or "") for t in trips if t.get("trailer")}
    trailers = {}
    if trailer_ids:
        for tr in session.scalars(
            select(VmsTrailer).where(VmsTrailer.tenant == ctx.tenant, VmsTrailer.uukey.in_(trailer_ids))
        ).all():
            trailers[tr.uukey] = tr

    slots: list[dict] = []
    for t in trips:
        vid = str(t.get("vehicle") or "")
        v = by_key.get(vid) or by_plate.get(vid.upper())
        goods = t.get("goods") or {}
        volume = _num(goods.get("volume"))
        tank_l = max(_num(goods.get("capacity"), 8000) or 8000, volume)
        tr = trailers.get(str(t.get("trailer") or ""))
        tanks = 1.0
        if tr is not None and tr.tanks:
            tanks = float(tr.tanks)
        elif v is not None and v.tanks:
            tanks = float(v.tanks)
        tanks = max(1.0, tanks)
        if pack == "stops":
            cap_kg = 10_000_000.0
            cap_pal = tanks
        else:
            cap_kg = tank_l
            cap_pal = tanks
        plate = (v.plate if v is not None else "") or vid
        slots.append(
            {
                "id": f"{vid}#{t['uukey']}",
                "vehicle_id": vid,
                "plate": plate,
                "capacity_kg": cap_kg,
                "capacity_pallets": cap_pal,
            }
        )
    return slots


def collect_trips(session, ctx, *, day: str | None, depot_filter: str | None, limit: int) -> list[dict]:
    from sqlalchemy import select

    from addon.fleet.domain.orm import VmsFreight

    stmt = select(VmsFreight).where(VmsFreight.tenant == ctx.tenant).order_by(VmsFreight.utime.desc())
    rows = list(session.scalars(stmt.limit(5000)).all())
    if not rows:
        return []
    days = [_day_key(r.utime) for r in rows]
    pick = day or next((d for d in days if d), "")
    out = []
    for r in rows:
        if _day_key(r.utime) != pick:
            continue
        depot = str(r.depot or "").strip()
        dest = str(r.dest or "").strip()
        if depot_filter and depot != depot_filter:
            continue
        if not depot or not dest:
            continue
        out.append(
            {
                "uukey": r.uukey or r.id,
                "utime": r.utime.isoformat() if r.utime else None,
                "day": pick,
                "vehicle": r.vehicle,
                "trailer": r.trailer,
                "depot": depot,
                "dest": dest,
                "bizType": r.bizType,
                "goods": dict(r.goods or {}),
            }
        )
        if len(out) >= limit:
            break
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync fleet.freight → freight.order and replay CVRP")
    parser.add_argument("--day", help="出车日期 YYYY-MM-DD（默认最新一天）")
    parser.add_argument("--depot", help="只跑某个油库名称")
    parser.add_argument("--limit", type=int, default=300, help="最多同步/求解多少条出车（默认 300）")
    parser.add_argument("--pack", choices=("liters", "stops"), default="liters", help="liters=升数+隔舱；stops=只按隔舱拼多卸")
    parser.add_argument("--time-limit", type=int, default=6, help="OR-Tools 秒数")
    parser.add_argument("--dry-run", action="store_true", help="不写 freight.order / dispatch.station")
    parser.add_argument("--force", action="store_true", help="覆盖已同步的 FL-* 订单")
    parser.add_argument("--no-geocode", action="store_true", help="跳过天地图地理编码，只用油库坐标+账面里程摆点")
    parser.add_argument("--open", action="store_true", help="用浏览器打开对比地图")
    parser.add_argument("--no-html", action="store_true")
    args = parser.parse_args(argv)

    from modoor.core.db import init_db, session_scope
    from modoor.core.settings import get_settings
    from modoor.platform.bootstrap import bootstrap
    from modoor.runtime.auth import resolve_ctx
    from addon.dispatch.domain.solver import plan_heuristic, plan_ortools

    get_settings.cache_clear()
    settings = get_settings()
    bootstrap(settings)
    init_db(settings)
    ctx = resolve_ctx(settings)

    with session_scope() as session:
        trips = collect_trips(session, ctx, day=args.day, depot_filter=args.depot, limit=args.limit)
        if not trips:
            print("没有可回放的 fleet.freight 出车（缺发站/到站，或日期不对）。")
            print("可先: make seed fleet FORCE=1")
            print("指定日期: --day YYYY-MM-DD")
            return 1

        day = trips[0]["day"]
        by_depot: dict[str, list[dict]] = defaultdict(list)
        for t in trips:
            by_depot[t["depot"]].append(t)

        from addon.dispatch import domain as dsp

        existing = load_station_index(session, ctx)
        tk = "" if args.no_geocode else dsp._tianditu_geocode_tk(session, ctx)
        geocode_cache: dict[str, tuple[float, float]] = {}
        sync_counts = {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "stations": 0,
            "geocoded": 0,
            "polar": 0,
        }

        def place(name: str, origin: tuple[float, float], rec_km: float = 0.0, *, jitter: bool = False) -> tuple[float, float]:
            lat, lng, source = resolve_coords(
                name, origin=origin, rec_km=rec_km, tk=tk, cache=geocode_cache, jitter=jitter
            )
            sync_counts[source] = sync_counts.get(source, 0) + 1
            return lat, lng

        depot_stations: dict[str, dict] = {}
        dest_stations_all: dict[str, dict] = {}
        for depot_name, depot_trips in by_depot.items():
            origin = NAME_COORDS.get(depot_name, LIANYUNGANG_CENTER)
            depot_lat, depot_lng = place(depot_name, origin, jitter=False)
            if not args.dry_run:
                depot_st = upsert_station(
                    session,
                    ctx,
                    name=depot_name,
                    kind="depot",
                    lat=depot_lat,
                    lng=depot_lng,
                    existing=existing,
                )
                sync_counts["stations"] += 1
            else:
                depot_st = existing.get(depot_name) or {
                    "uukey": station_code(depot_name),
                    "name": depot_name,
                    "lat": depot_lat,
                    "lng": depot_lng,
                }
            depot_stations[depot_name] = depot_st

            dest_names = sorted({t["dest"] for t in depot_trips})
            for name in dest_names:
                rec_km = dest_recorded_km(name, depot_trips)
                lat, lng = place(name, (depot_lat, depot_lng), rec_km, jitter=True)
                if not args.dry_run:
                    st = upsert_station(
                        session, ctx, name=name, kind="station", lat=lat, lng=lng, existing=existing
                    )
                    sync_counts["stations"] += 1
                else:
                    st = existing.get(name) or {
                        "uukey": station_code(name),
                        "name": name,
                        "lat": lat,
                        "lng": lng,
                    }
                dest_stations_all[name] = st

            for t in depot_trips:
                dest_st = dest_stations_all[t["dest"]]
                t["dest_name"] = dest_st.get("name") or t["dest"]
                t["dest_lat"] = float(dest_st["lat"])
                t["dest_lng"] = float(dest_st["lng"])
                t["order_id"] = f"{ORDER_PREFIX}{t['uukey']}"
                if not args.dry_run:
                    action = upsert_order(session, ctx, t, depot_st, dest_st, force=args.force)
                    sync_counts[action] = sync_counts.get(action, 0) + 1

        if not args.dry_run:
            dsp.save_map_setting(session, ctx, {"center": list(LIANYUNGANG_CENTER), "zoom": 9})
            sync_counts["yards"] = upsert_parking_yards(session, ctx, existing)

        if len(by_depot) > 1:
            print("同日多油库，已全部写入 freight.order：", {k: len(v) for k, v in by_depot.items()})

        if args.depot and args.depot in by_depot:
            depot_name, depot_trips = args.depot, by_depot[args.depot]
        else:
            depot_name, depot_trips = max(by_depot.items(), key=lambda kv: len(kv[1]))
        if len(by_depot) > 1:
            print("回放求解用单量最大油库：", depot_name)

        depot_st = depot_stations[depot_name]
        dest_stations = {t["dest"]: dest_stations_all[t["dest"]] for t in depot_trips}

        slots = build_assets(session, ctx, depot_trips, pack=args.pack)
        depot = {
            "id": depot_st.get("uukey") or station_code(depot_name),
            "name": depot_name,
            "lat": float(depot_st["lat"]),
            "lng": float(depot_st["lng"]),
        }
        demands = []
        demands_by_id = {}
        for t in depot_trips:
            goods = t.get("goods") or {}
            d = {
                "order_id": t["order_id"],
                "customer": t["dest"],
                "to_station": dest_stations[t["dest"]].get("uukey") or "",
                "unload_name": t["dest_name"],
                "lat": t["dest_lat"],
                "lng": t["dest_lng"],
                "weight": 0.0 if args.pack == "stops" else _num(goods.get("volume")),
                "pallets": 1.0,
                "quantity": _num(goods.get("quantity"), _num(goods.get("volume"))),
                "toll": _num(goods.get("tollFee")),
            }
            demands.append(d)
            demands_by_id[d["order_id"]] = d

        hist = historical_plan(depot, depot_trips, slots)
        heur = plan_heuristic(depot, demands, slots, max_unloads=8)
        ort = plan_ortools(depot, demands, slots, max_unloads=8, time_limit=args.time_limit)
        locked_fee = float(hist.get("recorded_fee") or 0)
        hist_km = float(hist.get("km") or 0)
        for p in (hist, heur, ort):
            attach_locked_fee(p, locked_fee, hist_km)

        whatif = None
        if args.pack == "liters":
            slots_s = build_assets(session, ctx, depot_trips, pack="stops")
            demands_s = [{**d, "weight": 0.0} for d in demands]
            whatif = plan_ortools(depot, demands_s, slots_s, max_unloads=8, time_limit=args.time_limit)
            whatif["name"] = "OR-Tools 假设：只按隔舱拼（忽略升数）"
            whatif["blurb"] = "升数不卡满时才能一装多卸。运费仍锁在需求上，省的是少跑的公里。"
            attach_locked_fee(whatif, locked_fee, hist_km)

        print(json.dumps(
            {
                "tenant": ctx.tenant,
                "day": day,
                "depot": depot_name,
                "trips": len(depot_trips),
                "all_trips": sum(len(v) for v in by_depot.values()),
                "depots": {k: len(v) for k, v in by_depot.items()},
                "unique_vehicles": len({str(t.get("vehicle") or "") for t in depot_trips}),
                "dests": sorted({t["dest"] for t in depot_trips}),
                "locked_fee": locked_fee,
                "sync": sync_counts,
                "dry_run": bool(args.dry_run),
                "pack": args.pack,
            },
            ensure_ascii=False,
        ))
        print(f"需求运费（锁死）{locked_fee}，各方案相同；只比里程/趟次。")
        print_plan(hist)
        print_plan(heur)
        print_plan(ort)
        if whatif:
            print_plan(whatif)

        better_km = hist["km"] - ort["km"]
        better_veh = hist["vehicles"] - ort["vehicles"]
        ort_gap = ort.get("unassigned") or []
        print("\n结论:")
        print("  运费跟定根需求走、锁死，排线省不了运费，只省里程（油耗/工时）。")
        if ort_gap:
            print(f"  OR-Tools 仍有 {len(ort_gap)} 单未派，不能算更优（先看罐容是否被单票打满）。")
        elif better_veh > 0 or better_km > 1:
            print(
                f"  卡罐容时相对历史少 {better_veh} 趟、直线少 {better_km:.1f} km。"
            )
        else:
            print(
                "  严格按罐容升数时，单票接近满罐，无法两站同车，压不出里程。"
            )
        if whatif:
            wgap = whatif.get("unassigned") or []
            extra = f"，未派 {len(wgap)}" if wgap else ""
            saved = hist["km"] - whatif["km"]
            print(
                f"  假设隔舱（可一车多站）：{whatif['vehicles']} 趟 / {whatif['km']} km，"
                f"比历史少 {saved:.1f} km、少 {hist['vehicles'] - whatif['vehicles']} 趟{extra}。"
                " 这才是可能省下的路。"
            )

        plans = [hist, heur, ort]
        if whatif:
            plans.append(whatif)
        if not args.no_html:
            path = write_html(
                depot,
                plans,
                title=f"{day} {depot_name} · {len(depot_trips)} 单回放",
                note=(
                    f"需求运费锁死 {locked_fee}，各方案相同。绿色 = 更少趟次/里程。"
                    " 站点按天地图地理编码落到苏北（齐湖在淮安，卸点在连云港）。"
                ),
            )
            print(f"\n地图: {path.resolve().as_uri()}")
            if args.open:
                webbrowser.open(path.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
