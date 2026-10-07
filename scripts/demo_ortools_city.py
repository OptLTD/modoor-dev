#!/usr/bin/env python3
"""Standalone 城配 OR-Tools demo — no DB, no API.

Compares current plan_city heuristic (greedy pack + NN + 2-opt)
against Google OR-Tools CVRP (weight + pallet capacity, open routes).

  .venv/bin/python scripts/demo_ortools_city.py
"""

from __future__ import annotations

import json
import math
import sys
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# Beijing 城配样本：大兴京南仓一装多卸
# 车辆刻意收紧容量，迫使拆多车，才能看出「分车 + 卸序」差异
# ---------------------------------------------------------------------------

DEPOT = {
    "id": "STABJ001",
    "name": "大兴京南仓",
    "lat": 39.7265,
    "lng": 116.3382,
}

STATIONS = {
    "STABJ002": {"name": "朝阳望京仓", "lat": 39.9962, "lng": 116.4806},
    "STABJ003": {"name": "海淀中关村仓", "lat": 39.9835, "lng": 116.3162},
    "STABJ004": {"name": "通州运河仓", "lat": 39.9028, "lng": 116.6580},
    "STABJ005": {"name": "顺义空港仓", "lat": 40.0801, "lng": 116.5948},
    "STABJ006": {"name": "丰台丽泽仓", "lat": 39.8630, "lng": 116.3345},
    "STABJ007": {"name": "昌平回龙观仓", "lat": 40.0705, "lng": 116.3360},
    "STABJ008": {"name": "亦庄经开仓", "lat": 39.7952, "lng": 116.5063},
}

ORDERS = [
    {"id": "ORDBJ001", "to": "STABJ002", "customer": "望京商超", "weight": 800, "pallets": 2},
    {"id": "ORDBJ002", "to": "STABJ003", "customer": "中关村电子城", "weight": 450, "pallets": 1},
    {"id": "ORDBJ003", "to": "STABJ004", "customer": "通州家居馆", "weight": 1200, "pallets": 3},
    {"id": "ORDBJ004", "to": "STABJ005", "customer": "空港冷链站", "weight": 600, "pallets": 2},
    {"id": "ORDBJ005", "to": "STABJ006", "customer": "丽泽写字楼配", "weight": 350, "pallets": 1},
    {"id": "ORDBJ006", "to": "STABJ007", "customer": "回龙观社区仓", "weight": 900, "pallets": 2},
    {"id": "ORDBJ007", "to": "STABJ008", "customer": "亦庄工厂线边", "weight": 1500, "pallets": 4},
    {"id": "ORDBJ008", "to": "STABJ002", "customer": "望京药店连锁", "weight": 280, "pallets": 1},
]

VEHICLES = [
    {"id": "VEHBJ001", "plate": "京A·C8001", "capacity_kg": 3000, "capacity_pallets": 8},
    {"id": "VEHBJ002", "plate": "京A·C8002", "capacity_kg": 3000, "capacity_pallets": 8},
    {"id": "VEHBJ003", "plate": "京A·C8003", "capacity_kg": 2000, "capacity_pallets": 6},
]

COLORS = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed"]
MAX_UNLOADS = 20
OUT_HTML = Path(__file__).with_suffix(".html")


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def demand_rows() -> list[dict]:
    rows = []
    for o in ORDERS:
        st = STATIONS[o["to"]]
        rows.append(
            {
                "order_id": o["id"],
                "customer": o["customer"],
                "to_station": o["to"],
                "unload_name": st["name"],
                "lat": st["lat"],
                "lng": st["lng"],
                "weight": o["weight"],
                "pallets": o["pallets"],
            }
        )
    return rows


def route_km(stops: list[dict]) -> float:
    total = 0.0
    for a, b in zip(stops, stops[1:]):
        total += haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
    return total


def nearest_neighbor(stations: list[dict], start: dict) -> list[dict]:
    remaining = [s for s in stations if s is not start]
    order = [start]
    while remaining:
        last = order[-1]
        nxt = min(remaining, key=lambda s: haversine_km(last["lat"], last["lng"], s["lat"], s["lng"]))
        remaining.remove(nxt)
        order.append(nxt)
    return order


def two_opt(order: list[dict]) -> list[dict]:
    if len(order) < 4:
        return list(order)
    best = list(order)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 2):
            for k in range(i + 1, len(best) - 1):
                cand = best[: i + 1] + best[i + 1 : k + 1][::-1] + best[k + 1 :]
                if route_km(cand) + 1e-9 < route_km(best):
                    best = cand
                    improved = True
    return best


def _stop(d: dict, *, kind: str = "unload") -> dict:
    if kind == "load":
        return {
            "kind": "load",
            "order_id": "",
            "name": DEPOT["name"],
            "customer": "",
            "lat": DEPOT["lat"],
            "lng": DEPOT["lng"],
            "weight": 0,
            "pallets": 0,
        }
    return {
        "kind": "unload",
        "order_id": d["order_id"],
        "name": d["unload_name"],
        "customer": d["customer"],
        "lat": d["lat"],
        "lng": d["lng"],
        "weight": d["weight"],
        "pallets": d["pallets"],
    }


def order_stops_heuristic(chosen: list[dict]) -> list[dict]:
    unload = [_stop(d) for d in chosen]
    if len(unload) >= 2:
        start = min(
            unload,
            key=lambda s: haversine_km(DEPOT["lat"], DEPOT["lng"], s["lat"], s["lng"]),
        )
        unload = two_opt(nearest_neighbor(unload, start))
    return [_stop({}, kind="load"), *unload]


def order_stops_as_is(chosen: list[dict]) -> list[dict]:
    return [_stop({}, kind="load"), *[_stop(d) for d in chosen]]


def waybill_from(asset: dict, chosen: list[dict], *, solver: str, reorder: bool) -> dict:
    stops = order_stops_heuristic(chosen) if reorder else order_stops_as_is(chosen)
    return {
        "solver": solver,
        "vehicle_id": asset["id"],
        "plate": asset["plate"],
        "capacity_kg": asset["capacity_kg"],
        "capacity_pallets": asset["capacity_pallets"],
        "load_kg": sum(d["weight"] for d in chosen),
        "load_pallets": sum(d["pallets"] for d in chosen),
        "orders": [d["order_id"] for d in chosen],
        "stops": stops,
        "km": round(route_km(stops), 1),
    }


def plan_heuristic(demands: list[dict], assets: list[dict]) -> dict:
    """Mirror addon.dispatch.domain.pack: largest vehicle first, nearest feasible order."""
    assets_sorted = sorted(
        assets,
        key=lambda a: (a["capacity_pallets"], a["capacity_kg"]),
        reverse=True,
    )
    pending = list(demands)
    waybills: list[dict] = []
    for asset in assets_sorted:
        if not pending:
            break
        cap_kg = asset["capacity_kg"]
        cap_pal = asset["capacity_pallets"]
        chosen: list[dict] = []
        load_kg = 0.0
        load_pal = 0.0
        cur_lat, cur_lng = DEPOT["lat"], DEPOT["lng"]
        remain = list(pending)
        while remain and len(chosen) < MAX_UNLOADS:
            cand_idx = -1
            cand_cost = 1e18
            for i, d in enumerate(remain):
                if load_kg + d["weight"] > cap_kg + 1e-6:
                    continue
                if load_pal + d["pallets"] > cap_pal + 1e-6:
                    continue
                dist = haversine_km(cur_lat, cur_lng, d["lat"], d["lng"])
                if dist < cand_cost:
                    cand_cost = dist
                    cand_idx = i
            if cand_idx < 0:
                break
            d = remain.pop(cand_idx)
            chosen.append(d)
            load_kg += d["weight"]
            load_pal += d["pallets"]
            cur_lat, cur_lng = d["lat"], d["lng"]
        if not chosen:
            continue
        taken = {d["order_id"] for d in chosen}
        pending = [d for d in pending if d["order_id"] not in taken]
        waybills.append(waybill_from(asset, chosen, solver="heuristic", reorder=True))
    return {
        "name": "启发式（当前 plan_city）",
        "blurb": "大车优先贪心塞单，再对每车到站做最近邻 + 2-opt。",
        "waybills": waybills,
        "unassigned": [d["order_id"] for d in pending],
        "km": round(sum(w["km"] for w in waybills), 1),
        "vehicles": len(waybills),
    }


def plan_ortools(demands: list[dict], assets: list[dict]) -> dict:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    n_orders = len(demands)
    n_vehicles = len(assets)
    # node 0 = depot, 1..n = orders
    nodes = [DEPOT, *demands]

    def dist_m(i: int, j: int) -> int:
        a, b = nodes[i], nodes[j]
        return int(round(haversine_km(a["lat"], a["lng"], b["lat"], b["lng"]) * 1000))

    manager = pywrapcp.RoutingIndexManager(n_orders + 1, n_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    def transit_cb(from_index: int, to_index: int) -> int:
        frm = manager.IndexToNode(from_index)
        to = manager.IndexToNode(to_index)
        if to == 0:  # open VRP: 不回站，回仓成本记 0
            return 0
        return dist_m(frm, to)

    transit_idx = routing.RegisterTransitCallback(transit_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    def weight_cb(from_index: int) -> int:
        node = manager.IndexToNode(from_index)
        return 0 if node == 0 else int(demands[node - 1]["weight"])

    def pallet_cb(from_index: int) -> int:
        node = manager.IndexToNode(from_index)
        return 0 if node == 0 else int(demands[node - 1]["pallets"])

    routing.AddDimensionWithVehicleCapacity(
        routing.RegisterUnaryTransitCallback(weight_cb),
        0,
        [int(a["capacity_kg"]) for a in assets],
        True,
        "Weight",
    )
    routing.AddDimensionWithVehicleCapacity(
        routing.RegisterUnaryTransitCallback(pallet_cb),
        0,
        [int(a["capacity_pallets"]) for a in assets],
        True,
        "Pallets",
    )

    # 用车有固定成本 → 能少开一辆就少开；距离单位是米
    for v in range(n_vehicles):
        routing.SetFixedCostOfVehicle(80_000, v)

    # 派不出去的单付大罚金，避免硬不可行直接无解
    for node in range(1, n_orders + 1):
        routing.AddDisjunction([manager.NodeToIndex(node)], 500_000)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromSeconds(3)
    params.log_search = False

    solution = routing.SolveWithParameters(params)
    if solution is None:
        return {
            "name": "OR-Tools CVRP",
            "blurb": "求解失败（无可行解）。",
            "waybills": [],
            "unassigned": [d["order_id"] for d in demands],
            "km": 0,
            "vehicles": 0,
        }

    assigned: set[str] = set()
    waybills: list[dict] = []
    for v in range(n_vehicles):
        index = routing.Start(v)
        chosen: list[dict] = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != 0:
                chosen.append(demands[node - 1])
            index = solution.Value(routing.NextVar(index))
        if not chosen:
            continue
        assigned.update(d["order_id"] for d in chosen)
        waybills.append(waybill_from(assets[v], chosen, solver="ortools", reorder=False))

    return {
        "name": "OR-Tools CVRP",
        "blurb": "重量+托位双容量约束，一次同时决定分车和卸序；不回站。",
        "waybills": waybills,
        "unassigned": [d["order_id"] for d in demands if d["order_id"] not in assigned],
        "km": round(sum(w["km"] for w in waybills), 1),
        "vehicles": len(waybills),
    }


def print_plan(plan: dict) -> None:
    print(f"\n=== {plan['name']} ===")
    print(plan["blurb"])
    print(f"用车 {plan['vehicles']} 辆  总里程 {plan['km']} km  未派 {plan['unassigned'] or '无'}")
    for w in plan["waybills"]:
        seq = " → ".join(s["name"] for s in w["stops"])
        print(
            f"  {w['plate']}  {w['load_kg']}kg/{w['capacity_kg']}  "
            f"{w['load_pallets']}托/{w['capacity_pallets']}  {w['km']}km"
        )
        print(f"    {seq}")
        print(f"    订单 {', '.join(w['orders'])}")


def write_html(heuristic: dict, ortools_plan: dict) -> Path:
    payload = {
        "depot": DEPOT,
        "heuristic": heuristic,
        "ortools": ortools_plan,
        "colors": COLORS,
        "orders": demand_rows(),
        "vehicles": VEHICLES,
    }
    html = _HTML.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
    OUT_HTML.write_text(html, encoding="utf-8")
    return OUT_HTML


_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>城配 OR-Tools Demo</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  :root { --bg:#0f172a; --card:#1e293b; --line:#334155; --txt:#e2e8f0; --muted:#94a3b8; --acc:#38bdf8; }
  * { box-sizing: border-box; }
  html, body { margin:0; height:100%; font-family: ui-sans-serif, system-ui, "PingFang SC", "Noto Sans SC", sans-serif; background:var(--bg); color:var(--txt); }
  .wrap { display:grid; grid-template-rows: auto 1fr; height:100%; }
  header { padding:16px 20px 12px; border-bottom:1px solid var(--line); }
  header h1 { margin:0 0 6px; font-size:18px; font-weight:650; }
  header p { margin:0; color:var(--muted); font-size:13px; line-height:1.5; }
  .cols { display:grid; grid-template-columns: 1fr 1fr; min-height:0; }
  .pane { display:grid; grid-template-rows: auto auto 1fr; min-height:0; border-right:1px solid var(--line); }
  .pane:last-child { border-right:none; }
  .stats { display:flex; gap:10px; padding:12px 16px; }
  .stat { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px 12px; min-width:88px; }
  .stat b { display:block; font-size:18px; }
  .stat span { color:var(--muted); font-size:11px; }
  .stat.win b { color:#34d399; }
  .legend { padding:0 16px 8px; font-size:12px; color:var(--muted); }
  .map { height: 44vh; min-height: 340px; }
  .list { padding:10px 16px 16px; overflow:auto; font-size:13px; }
  .wb { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin-bottom:8px; }
  .wb h3 { margin:0 0 4px; font-size:13px; display:flex; justify-content:space-between; }
  .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }
  .seq { color:var(--muted); line-height:1.45; }
  @media (max-width: 720px) { .cols { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>城配一装多卸 · OR-Tools vs 启发式</h1>
    <p>发站固定大兴京南仓；约束 = 载重 + 托位；线路不回仓。左边是现在 <code>plan_city</code> 的贪心，右边是 Google OR-Tools 一次求解分车+卸序。</p>
  </header>
  <div class="cols">
    <section class="pane" id="left"></section>
    <section class="pane" id="right"></section>
  </div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const DATA = __PAYLOAD__;

function renderPane(el, plan, mapId, winKm) {
  const stats = document.createElement('div');
  stats.className = 'stats';
  const items = [
    [plan.vehicles + ' 辆', '用车'],
    [plan.km + ' km', '总里程'],
    [(plan.unassigned || []).length, '未派单'],
  ];
  stats.innerHTML = items.map(([v, l], i) => {
    const win = i === 1 && plan.km === winKm ? ' win' : '';
    return `<div class="stat${win}"><b>${v}</b><span>${l}</span></div>`;
  }).join('') + `<div class="stat"><b>${plan.name.split('（')[0]}</b><span>求解器</span></div>`;
  const legend = document.createElement('div');
  legend.className = 'legend';
  legend.textContent = plan.blurb;
  const mapDiv = document.createElement('div');
  mapDiv.className = 'map';
  mapDiv.id = mapId;
  const list = document.createElement('div');
  list.className = 'list';
  list.innerHTML = plan.waybills.map((w, i) => {
    const color = DATA.colors[i % DATA.colors.length];
    const seq = w.stops.map(s => s.name).join(' → ');
    return `<div class="wb">
      <h3><span><i class="dot" style="background:${color}"></i>${w.plate}</span>
          <span>${w.load_kg}kg / ${w.load_pallets}托 · ${w.km}km</span></h3>
      <div class="seq">${seq}</div>
      <div class="seq">订单 ${w.orders.join('、')}</div>
    </div>`;
  }).join('') || '<div class="wb">无运单</div>';
  el.append(stats, legend, mapDiv, list);

  const map = L.map(mapId, { zoomControl: true });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18, attribution: '&copy; OpenStreetMap'
  }).addTo(map);
  const bounds = [];
  const depot = DATA.depot;
  const dMarker = L.circleMarker([depot.lat, depot.lng], {
    radius: 8, color: '#fbbf24', fillColor: '#fbbf24', fillOpacity: 1, weight: 2
  }).addTo(map).bindPopup('发站 · ' + depot.name);
  bounds.push([depot.lat, depot.lng]);
  plan.waybills.forEach((w, i) => {
    const color = DATA.colors[i % DATA.colors.length];
    const latlngs = w.stops.map(s => [s.lat, s.lng]);
    latlngs.forEach(ll => bounds.push(ll));
    L.polyline(latlngs, { color, weight: 4, opacity: 0.85 }).addTo(map);
    w.stops.forEach((s, idx) => {
      if (idx === 0) return;
      L.circleMarker([s.lat, s.lng], {
        radius: 6, color, fillColor: '#0f172a', fillOpacity: 1, weight: 3
      }).addTo(map).bindPopup(`${w.plate} 卸 ${idx}. ${s.name}<br/>${s.customer || ''} ${s.weight}kg / ${s.pallets}托`);
    });
  });
  map.fitBounds(bounds, { padding: [24, 24] });
  setTimeout(() => map.invalidateSize(), 80);
}

const winKm = Math.min(DATA.heuristic.km, DATA.ortools.km);
renderPane(document.getElementById('left'), DATA.heuristic, 'map-h', winKm);
renderPane(document.getElementById('right'), DATA.ortools, 'map-o', winKm);
</script>
</body>
</html>
"""


def main() -> int:
    try:
        import ortools  # noqa: F401
    except ImportError:
        print("缺少 ortools，正在安装…")
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "ortools"])

    demands = demand_rows()
    heuristic = plan_heuristic(demands, VEHICLES)
    ortools_plan = plan_ortools(demands, VEHICLES)
    print_plan(heuristic)
    print_plan(ortools_plan)
    delta = heuristic["km"] - ortools_plan["km"]
    print(
        f"\n对比: OR-Tools 总里程 {ortools_plan['km']} km，"
        f"启发式 {heuristic['km']} km，差值 {delta:+.1f} km"
    )
    path = write_html(heuristic, ortools_plan)
    uri = path.resolve().as_uri()
    print(f"\n地图: {uri}")
    if "--no-open" not in sys.argv:
        webbrowser.open(uri)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
