#!/usr/bin/env python3
"""Compare historical assignment encoded in freight.order uukey vs current auto plan."""

from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYTHONPATH", str(ROOT))

from modoor.core.db import init_db, session_scope
from modoor.core.settings import get_settings
from modoor.platform.bootstrap import bootstrap
from modoor.runtime.auth import resolve_ctx

from addon.dispatch import domain as dsp

UUKEY_RE = re.compile(
    r"^(?:FL-)?SDL-(\d{8})-(.+)-(\d+)-(\d+)$",
    re.IGNORECASE,
)


def _norm_plate(p: str) -> str:
    return str(p or "").replace(" ", "").upper()


def parse_order_id(oid: str) -> dict | None:
    m = UUKEY_RE.match(str(oid or "").strip())
    if not m:
        return None
    return {
        "date": m.group(1),
        "plate": m.group(2),
        "trip": int(m.group(3)),
        "stop": int(m.group(4)),
    }


def station_index(stations: list[dict]) -> dict[str, dict]:
    by: dict[str, dict] = {}
    for s in stations:
        for key in (s.get("uukey"), s.get("name"), str(s.get("name") or "").lower()):
            if key:
                by[str(key)] = s
    return by


def resolve_st(key: str, by: dict[str, dict], name: str = "") -> dict | None:
    if key and key in by:
        return by[key]
    if name and name in by:
        return by[name]
    low = name.lower() if name else ""
    return by.get(low) if low else None


def build_trip_stops(
    *,
    depot: dict,
    yard: dict | None,
    unloads: list[dict],
    last_of_day: bool,
) -> list[dict]:
    stops: list[dict] = []
    if yard:
        stops.append(
            {
                "kind": "yard",
                "name": yard.get("name") or "停车场",
                "lat": yard.get("lat"),
                "lng": yard.get("lng"),
                "ref_id": yard.get("uukey") or "",
            }
        )
    stops.append(
        {
            "kind": "load",
            "name": depot.get("name") or "油库",
            "lat": depot.get("lat"),
            "lng": depot.get("lng"),
            "ref_id": depot.get("uukey") or "",
        }
    )
    for d in unloads:
        stops.append(
            {
                "kind": "unload",
                "name": d.get("unload_name") or d.get("to_station") or "",
                "lat": d.get("lat"),
                "lng": d.get("lng"),
                "ref_id": d.get("to_station") or "",
                "order_id": d.get("order_id") or "",
            }
        )
    if last_of_day and yard:
        stops.append(
            {
                "kind": "yard",
                "name": yard.get("name") or "停车场",
                "lat": yard.get("lat"),
                "lng": yard.get("lng"),
                "ref_id": yard.get("uukey") or "",
            }
        )
    else:
        stops.append(
            {
                "kind": "load",
                "name": depot.get("name") or "油库",
                "lat": depot.get("lat"),
                "lng": depot.get("lng"),
                "ref_id": depot.get("uukey") or "",
            }
        )
    return stops


def trip_kpis(stops: list[dict]) -> tuple[float, float]:
    total = 0.0
    empty = 0.0
    for a, b in zip(stops, stops[1:]):
        try:
            km = dsp._haversine_km(float(a["lat"]), float(a["lng"]), float(b["lat"]), float(b["lng"]))
        except (TypeError, ValueError, KeyError):
            km = 0.0
        total += km
        if dsp._leg_is_empty(a, b):
            empty += km
    return total, empty


def waybill_from_group(
    *,
    plate: str,
    trip_no: int,
    depot: dict,
    yard: dict | None,
    rows: list[dict],
    last_of_day: bool,
) -> dict:
    unloads = sorted(rows, key=lambda d: int((d.get("hist") or {}).get("stop") or 0))
    stops = build_trip_stops(depot=depot, yard=yard, unloads=unloads, last_of_day=last_of_day)
    km, empty = trip_kpis(stops)
    liters = sum(float(d.get("weight") or 0) for d in unloads)
    return {
        "plate": plate,
        "trip_no": trip_no,
        "depot": depot.get("name") or "",
        "stations": [d.get("unload_name") or d.get("to_station") or "" for d in unloads],
        "order_ids": [d["order_id"] for d in unloads],
        "stops": len(unloads),
        "liters": round(liters, 1),
        "km": round(km, 2),
        "empty_km": round(empty, 2),
        "empty_rate": round(empty / km, 4) if km else 0.0,
        "route": " → ".join(s["name"] for s in stops if s.get("name")),
    }


def _trailer_to_tractor(session, ctx) -> dict[str, str]:
    from sqlalchemy import select

    from addon.fleet.domain.orm import VmsFreight, VmsTrailer, VmsVehicle

    trailers = list(
        session.scalars(select(VmsTrailer).where(VmsTrailer.tenant == ctx.tenant)).all()
    )
    vehicles = list(
        session.scalars(select(VmsVehicle).where(VmsVehicle.tenant == ctx.tenant)).all()
    )
    frs = list(session.scalars(select(VmsFreight).where(VmsFreight.tenant == ctx.tenant)).all())
    tr_by_key = {}
    for t in trailers:
        snap = {"plate": str(t.plate or "").strip(), "uukey": str(t.uukey or "").strip()}
        for k in (t.uukey, t.plate):
            if k:
                tr_by_key[_norm_plate(k)] = snap
    veh_by_key = {}
    for v in vehicles:
        snap = {"plate": str(v.plate or "").strip(), "uukey": str(v.uukey or "").strip(), "trailer": str(v.trailer or "").strip()}
        for k in (v.uukey, v.plate):
            if k:
                veh_by_key[_norm_plate(k)] = snap

    out: dict[str, str] = {}

    def bind(trailer_key: str, tractor_plate: str) -> None:
        tk, tp = _norm_plate(trailer_key), str(tractor_plate or "").strip()
        if tk and tp:
            out[tk] = tp

    for v in vehicles:
        tractor = str(v.plate or "").strip()
        raw = str(v.trailer or "").strip()
        if not tractor or not raw:
            continue
        bind(raw, tractor)
        tr = tr_by_key.get(_norm_plate(raw))
        if tr:
            bind(tr["plate"], tractor)
            bind(tr["uukey"], tractor)
    for r in frs:
        v = veh_by_key.get(_norm_plate(r.vehicle))
        tractor = (v or {}).get("plate") or ""
        raw = str(r.trailer or "").strip()
        if not tractor or not raw:
            continue
        bind(raw, tractor)
        tr = tr_by_key.get(_norm_plate(raw))
        if tr:
            bind(tr["plate"], tractor)
            bind(tr["uukey"], tractor)
    for v in vehicles:
        if v.plate:
            bind(v.plate, v.plate)
    return {k: v for k, v in out.items() if k and v}


def compact_auto(w: dict, demand_liters: dict[str, float]) -> dict:
    unloads = [s for s in (w.get("stops") or []) if s.get("kind") == "unload"]
    load = next((s for s in (w.get("stops") or []) if s.get("kind") == "load"), None)
    oids = list(w.get("order_ids") or [])
    return {
        "plate": w.get("plate") or "",
        "vehicle_id": w.get("vehicle_id") or "",
        "depot": (load or {}).get("name") or w.get("depot_name") or "",
        "stations": [s.get("name") or "" for s in unloads],
        "order_ids": oids,
        "stops": len(unloads),
        "liters": round(sum(demand_liters.get(oid, 0.0) for oid in oids), 1),
        "packed_l": round(float(w.get("load_kg") or 0), 1),
        "km": round(float(w.get("distance_km") or 0), 2),
        "empty_km": round(float(w.get("empty_km") or 0), 2),
        "empty_rate": round(float(w.get("empty_km_rate") or 0), 4),
        "route": " → ".join(s.get("name") or "" for s in (w.get("stops") or [])),
    }


def summarize(waybills: list[dict]) -> dict:
    km = sum(float(w.get("km") or 0) for w in waybills)
    empty = sum(float(w.get("empty_km") or 0) for w in waybills)
    liters = sum(float(w.get("liters") or 0) for w in waybills)
    plates = {w.get("plate") for w in waybills if w.get("plate")}
    stops = [int(w.get("stops") or 0) for w in waybills]
    return {
        "trips": len(waybills),
        "vehicles": len(plates),
        "orders": sum(len(w.get("order_ids") or []) for w in waybills),
        "km": round(km, 2),
        "empty_km": round(empty, 2),
        "empty_rate": round(empty / km, 4) if km else 0.0,
        "liters": round(liters, 1),
        "avg_stops": round(sum(stops) / len(stops), 2) if stops else 0.0,
        "max_stops": max(stops) if stops else 0,
        "trips_1stop": sum(1 for n in stops if n == 1),
        "trips_2stop": sum(1 for n in stops if n == 2),
        "trips_3plus": sum(1 for n in stops if n >= 3),
    }


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    bootstrap(settings)
    init_db(settings)
    ctx = resolve_ctx(settings)

    with session_scope() as session:
        demand = dsp.list_demand(session, ctx, limit=400)
        assets = dsp.list_assets(session, ctx, limit=200)
        stations = [
            dsp._station_point(dsp._to_values(r))
            for r in dsp._list_docs(session, ctx, dsp.DspStation)
        ]
        by_st = station_index(stations)
        yards = dsp._list_yards(session, ctx)
        saved = dsp.load_saved_plan(session, ctx, mode="fuel")
        trailer_to_tractor = _trailer_to_tractor(session, ctx)

    items = list(demand.get("items") or [])
    parsed, skipped = [], []
    for d in items:
        hist = parse_order_id(str(d.get("order_id") or ""))
        if not hist:
            skipped.append(d.get("order_id"))
            continue
        row = dict(d)
        row["hist"] = hist
        parsed.append(row)

    groups: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
    by_plate_trips: dict[tuple[str, str], set[int]] = defaultdict(set)
    for d in parsed:
        h = d["hist"]
        groups[(h["date"], h["plate"], h["trip"])].append(d)
        by_plate_trips[(h["date"], h["plate"])].add(h["trip"])

    hist_waybills = []
    missing_geo = []
    for (date, plate, trip_no), rows in sorted(groups.items()):
        first = rows[0]
        depot = resolve_st(str(first.get("from_station") or ""), by_st, first.get("from_name") or "")
        if depot is None or depot.get("lat") is None:
            missing_geo.append({"plate": plate, "trip": trip_no, "reason": "no_depot"})
            continue
        if any(r.get("lat") is None or r.get("lng") is None for r in rows):
            missing_geo.append({"plate": plate, "trip": trip_no, "reason": "missing_unload_coords"})
            continue
        yard = dsp._pick_yard(depot, yards)
        last = trip_no == max(by_plate_trips[(date, plate)])
        tractor = trailer_to_tractor.get(_norm_plate(plate)) or plate
        wb = waybill_from_group(
            plate=plate,
            trip_no=trip_no,
            depot=depot,
            yard=yard,
            rows=rows,
            last_of_day=last,
        )
        wb["trailer"] = plate
        wb["plate"] = tractor
        hist_waybills.append(wb)

    demand_liters = {str(d.get("order_id") or ""): float(d.get("weight") or 0) for d in parsed}

    plan = saved.get("plan") or {}
    schemes = plan.get("scheme_plans") or {}
    auto_sets = {}
    for key in ("shortest", "fill", "manual"):
        slice_ = schemes.get(key) or {}
        wbs = [compact_auto(w, demand_liters) for w in (slice_.get("waybills") or [])]
        # fill empty_km if waybill didn't persist it
        for w, raw in zip(wbs, slice_.get("waybills") or []):
            if not w["empty_km"] and raw.get("stops"):
                km, empty = trip_kpis(raw.get("stops") or [])
                w["km"] = round(km, 2)
                w["empty_km"] = round(empty, 2)
                w["empty_rate"] = round(empty / km, 4) if km else 0.0
        kpis = slice_.get("kpis") or {}
        auto_sets[key] = {
            "name": {"shortest": "最短路径", "fill": "最低空驶", "manual": "人工安排"}.get(key, key),
            "summary": summarize(wbs),
            "kpis": {
                "distance_km": kpis.get("distance_km"),
                "empty_km": kpis.get("empty_km"),
                "empty_km_rate": kpis.get("empty_km_rate"),
                "trips": kpis.get("trips"),
                "vehicles": kpis.get("vehicles"),
            },
            "waybills": wbs,
            "unassigned": len(slice_.get("unassigned") or []),
        }

    # assignment comparison vs shortest (current UI default)
    auto = auto_sets.get("shortest") or {"waybills": []}
    hist_assign = {}
    for w in hist_waybills:
        for oid in w["order_ids"]:
            hist_assign[oid] = {
                "plate": w["plate"],
                "trip": w["trip_no"],
                "depot": w["depot"],
                "station": next(
                    (s for s, i in zip(w["stations"], w["order_ids"]) if i == oid),
                    "",
                ),
            }
    auto_assign = {}
    for w in auto.get("waybills") or []:
        for oid in w["order_ids"]:
            auto_assign[oid] = {
                "plate": w["plate"],
                "depot": w["depot"],
                "stations": w["stations"],
            }

    same_plate = 0
    changed_plate = []
    changed_group = []
    only_hist = []
    only_auto = []
    for oid, h in hist_assign.items():
        a = auto_assign.get(oid)
        if a is None:
            only_hist.append(oid)
            continue
        hp, ap = _norm_plate(h["plate"]), _norm_plate(a["plate"])
        if hp and ap and (hp == ap or hp in ap or ap in hp):
            same_plate += 1
        else:
            changed_plate.append(
                {
                    "order_id": oid,
                    "station": h["station"],
                    "hist_plate": h["plate"],
                    "auto_plate": a["plate"],
                    "hist_depot": h["depot"],
                    "auto_depot": a.get("depot") or "",
                }
            )
        # grouping: same plate's same-trip partners
        hist_mates = set()
        for w in hist_waybills:
            if oid in w["order_ids"]:
                hist_mates = set(w["order_ids"]) - {oid}
                break
        auto_mates = set()
        for w in auto.get("waybills") or []:
            if oid in w["order_ids"]:
                auto_mates = set(w["order_ids"]) - {oid}
                break
        if hist_mates != auto_mates:
            changed_group.append(oid)

    for oid in auto_assign:
        if oid not in hist_assign:
            only_auto.append(oid)

    # per plate trip counts
    hist_by_plate: dict[str, list[dict]] = defaultdict(list)
    for w in hist_waybills:
        hist_by_plate[_norm_plate(w["plate"])].append(w)
    auto_by_plate: dict[str, list[dict]] = defaultdict(list)
    for w in auto.get("waybills") or []:
        auto_by_plate[_norm_plate(w["plate"])].append(w)

    plate_rows = []
    all_plates = sorted(set(hist_by_plate) | set(auto_by_plate))
    for p in all_plates:
        hw, aw = hist_by_plate.get(p, []), auto_by_plate.get(p, [])
        plate_rows.append(
            {
                "plate": hw[0]["plate"] if hw else (aw[0]["plate"] if aw else p),
                "hist_trips": len(hw),
                "auto_trips": len(aw),
                "hist_stops": sum(x["stops"] for x in hw),
                "auto_stops": sum(x["stops"] for x in aw),
                "hist_km": round(sum(x["km"] for x in hw), 1),
                "auto_km": round(sum(x["km"] for x in aw), 1),
                "hist_route": " | ".join(" / ".join(x["stations"]) for x in hw),
                "auto_route": " | ".join(" / ".join(x["stations"]) for x in aw),
            }
        )

    # depot mix
    def depot_counts(wbs):
        c: dict[str, int] = defaultdict(int)
        for w in wbs:
            c[w.get("depot") or "未知"] += 1
        return dict(sorted(c.items(), key=lambda kv: -kv[1]))

    hist_sum = summarize(hist_waybills)
    auto_sum = auto.get("summary") or {}
    fill_sum = (auto_sets.get("fill") or {}).get("summary") or {}

    sample_hist = sorted(hist_waybills, key=lambda w: (w["plate"], w["trip_no"]))[:18]
    sample_auto = (auto.get("waybills") or [])[:18]

    # dates
    dates = sorted({d["hist"]["date"] for d in parsed})
    mapped = sum(1 for d in parsed if trailer_to_tractor.get(_norm_plate(d["hist"]["plate"])))
    unique_stations_hist = [len(set(w["stations"])) for w in hist_waybills]
    unique_stations_auto = [len(set(w["stations"])) for w in (auto.get("waybills") or [])]
    hist_sum["unique_stops_avg"] = round(sum(unique_stations_hist) / len(unique_stations_hist), 2) if unique_stations_hist else 0
    auto_sum["unique_stops_avg"] = round(sum(unique_stations_auto) / len(unique_stations_auto), 2) if unique_stations_auto else 0
    hist_sum["trips_4stop"] = sum(1 for w in hist_waybills if w["stops"] >= 4)
    auto_sum["same_plate_orders"] = same_plate
    km_delta = round(float(auto_sum.get("km") or 0) - float(hist_sum.get("km") or 0), 2)
    empty_delta = round(float(auto_sum.get("empty_km") or 0) - float(hist_sum.get("empty_km") or 0), 2)

    out = {
        "batch_id": saved.get("batch_id") or "",
        "dates": dates,
        "order_count": len(parsed),
        "skipped": skipped,
        "missing_geo": missing_geo,
        "hist": hist_sum,
        "shortest": auto_sum,
        "fill": fill_sum,
        "manual": (auto_sets.get("manual") or {}).get("summary") or {},
        "assignment": {
            "same_plate": same_plate,
            "changed_plate": len(changed_plate),
            "changed_group": len(changed_group),
            "only_hist": len(only_hist),
            "only_auto": len(only_auto),
            "match_rate": round(same_plate / len(hist_assign), 4) if hist_assign else 0,
        },
        "changed_plate_rows": sorted(changed_plate, key=lambda r: r["hist_plate"])[:40],
        "plate_rows": plate_rows,
        "hist_depots": depot_counts(hist_waybills),
        "auto_depots": depot_counts(auto.get("waybills") or []),
        "hist_samples": sample_hist,
        "auto_samples": sample_auto,
        "uukey_example": parsed[0]["order_id"] if parsed else "",
        "trailer_map_hit": mapped,
        "trailer_map_size": len(trailer_to_tractor),
        "deltas": {
            "km": km_delta,
            "empty_km": empty_delta,
            "trips": int(auto_sum.get("trips") or 0) - int(hist_sum.get("trips") or 0),
            "vehicles": int(auto_sum.get("vehicles") or 0) - int(hist_sum.get("vehicles") or 0),
        },
    }

    dest = ROOT / "scripts" / "compare_hist_auto_dispatch.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in (
        "batch_id", "dates", "order_count", "hist", "shortest", "fill", "assignment"
    )}, ensure_ascii=False, indent=2))
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
