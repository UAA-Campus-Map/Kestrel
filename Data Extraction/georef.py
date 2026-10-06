"""Georeference extracted floor plans: CAD x,y -> lon/lat.

Each floor has a hand-editable file georef/<code>-<level>.json that holds its
control points (a CAD point and the lon/lat it belongs at) and optional field
checks (a distance measured on campus between two CAD points). This script
fits a similarity transform (scale + rotation + offset) to the points and
writes the result into the file's "fit" block. To correct a floor, edit its
points (add field data, set "use": false on a bad one) and run fit again.

    python georef.py init AS101-01 --from-prototype esh
    python georef.py fit AS101-01 [--holdout]
    python georef.py preview AS101-01

See georef/README.md for the full procedure.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from floorplan_extractor import DEFAULT_OUT_DIR, building_info

HERE = Path(__file__).resolve().parent
GEOREF_DIR = HERE / "georef"
PREVIEW_DIR = GEOREF_DIR / "preview"
PROTOTYPE_HTML = HERE.parent / "Oropendula" / "src" / "index.html"

INCH_M = 0.0254         # DXFs are drawn in inches (36-unit door swings)
FLAG_FACTOR = 3.0       # flag residuals above this many times the median...
FLAG_MIN_M = 1.0        # ...but never below this, so a tight fit doesn't flag everything


# ---------------------------------------------------------------------------
# lon/lat <-> local east/north plane in meters
# ---------------------------------------------------------------------------

def meters_per_degree(lat):
    """(meters per degree of longitude, meters per degree of latitude) on
    WGS84 at this latitude. Over a single building (<300 m) treating these as
    constant is accurate to well under a centimeter."""
    p = np.radians(lat)
    m_lat = 111132.92 - 559.82 * np.cos(2 * p) + 1.175 * np.cos(4 * p)
    m_lon = 111412.84 * np.cos(p) - 93.5 * np.cos(3 * p)
    return m_lon, m_lat


def to_plane(lonlat, ref):
    lonlat = np.asarray(lonlat, dtype=float)
    m_lon, m_lat = meters_per_degree(ref[1])
    return np.column_stack([(lonlat[:, 0] - ref[0]) * m_lon, (lonlat[:, 1] - ref[1]) * m_lat])


def from_plane(en, ref):
    en = np.asarray(en, dtype=float)
    m_lon, m_lat = meters_per_degree(ref[1])
    return np.column_stack([en[:, 0] / m_lon + ref[0], en[:, 1] / m_lat + ref[1]])


# ---------------------------------------------------------------------------
# similarity fit
# ---------------------------------------------------------------------------

def fit_similarity(cad, lonlat, scale=None):
    """Least-squares similarity transform from CAD points to lon/lat.

    Works in complex numbers: with both point sets centered on their
    centroids, east+i*north = a * (x+i*y), where |a| is the scale (meters per
    CAD unit) and arg(a) the rotation. This form can't produce a mirror
    image, which a CAD drawing never needs. Pass scale (m per CAD unit) to
    trust the drawing's own scale and fit only rotation and offset."""
    cad = np.asarray(cad, dtype=float)
    lonlat = np.asarray(lonlat, dtype=float)
    if len(cad) < 2:
        raise ValueError("need at least 2 control points (3+ to measure error)")

    cad_ref = cad.mean(axis=0)
    ref = lonlat.mean(axis=0)
    w = (cad[:, 0] - cad_ref[0]) + 1j * (cad[:, 1] - cad_ref[1])
    en = to_plane(lonlat, ref)
    z = en[:, 0] + 1j * en[:, 1]
    a = np.sum(np.conj(w) * z) / np.sum(np.abs(w) ** 2)
    if scale is not None:
        a = scale * np.exp(1j * np.angle(a))
    return {
        "type": "similarity",
        "cad_ref": [round(float(cad_ref[0]), 4), round(float(cad_ref[1]), 4)],
        "ref_lonlat": [round(float(ref[0]), 9), round(float(ref[1]), 9)],
        "scale_m_per_unit": float(abs(a)),
        "rotation_deg": float(np.degrees(np.angle(a))),
    }


def apply(transform, cad):
    """CAD points (N x 2) -> lon/lat (N x 2)."""
    cad = np.asarray(cad, dtype=float).reshape(-1, 2)
    a = transform["scale_m_per_unit"] * np.exp(1j * np.radians(transform["rotation_deg"]))
    x0, y0 = transform["cad_ref"]
    z = a * ((cad[:, 0] - x0) + 1j * (cad[:, 1] - y0))
    return from_plane(np.column_stack([z.real, z.imag]), transform["ref_lonlat"])


def residuals_m(transform, cad, lonlat):
    """Distance in meters between each fitted point and where it should be."""
    ref = transform["ref_lonlat"]
    return np.linalg.norm(to_plane(apply(transform, cad), ref) - to_plane(lonlat, ref), axis=1)


def flag_outliers(res):
    """Indices of residuals that look like mistakes rather than noise."""
    limit = max(FLAG_FACTOR * float(np.median(res)), FLAG_MIN_M)
    return [i for i, r in enumerate(res) if r > limit]


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------

def georef_path(floor):
    return GEOREF_DIR / f"{floor}.json"


def floor_json(floor):
    path = DEFAULT_OUT_DIR / f"{floor}.json"
    if not path.exists():
        sys.exit(f"{path} not found -- run floorplan_extractor.py on {floor}.dxf first")
    return json.loads(path.read_text(encoding="utf-8"))


def load(floor):
    path = georef_path(floor)
    if not path.exists():
        sys.exit(f"{path} not found -- run: python georef.py init {floor}")
    return json.loads(path.read_text(encoding="utf-8"))


def save(floor, data):
    """Write with one control point / check / residual per line, so the file
    stays easy to read and edit by hand."""
    def rows(items):
        if not items:
            return "[]"
        return "[\n" + ",\n".join("    " + json.dumps(v) for v in items) + "\n  ]"

    parts = []
    for k, v in data.items():
        if k in ("control_points", "checks"):
            parts.append(f'  "{k}": {rows(v)}')
        elif k == "fit" and v:
            fit = [f'    "{fk}": {rows(fv) if fk in ("residuals", "check_results") else json.dumps(fv)}'
                   for fk, fv in v.items()]
            parts.append('  "fit": {\n' + ",\n".join(fit) + "\n  }")
        else:
            parts.append(f"  {json.dumps(k)}: {json.dumps(v)}")
    GEOREF_DIR.mkdir(exist_ok=True)
    georef_path(floor).write_text("{\n" + ",\n".join(parts) + "\n}\n", encoding="utf-8")


def prototype_buildings(html_path):
    """The prototype's hardcoded buildings array: one JSON object per line."""
    out = {}
    for line in Path(html_path).read_text(encoding="utf-8").splitlines():
        line = line.strip().rstrip(",")
        if line.startswith('{"name"'):
            b = json.loads(line)
            out[b["name"]] = b
    return out


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_init(args):
    floor = args.floor.upper()
    if georef_path(floor).exists() and not args.force:
        sys.exit(f"{georef_path(floor)} already exists (it may have hand edits) -- pass --force to replace it")

    info = building_info(floor)
    plan = floor_json(floor)
    data = {"building_code": info["building_code"], "ID": info["ID"],
            "building_name": info["building_name"], "level": info["level"],
            "control_points": [], "checks": [], "fit": {}}

    if args.from_prototype:
        protos = prototype_buildings(args.prototype)
        if args.from_prototype not in protos:
            sys.exit(f"no prototype building '{args.from_prototype}' (have: {', '.join(protos)})")

        labels = {}
        for t in plan["text_lines"]:
            labels.setdefault(t["text"].upper(), []).append((t["x"], t["y"]))

        unmatched, ambiguous = [], []
        for room in protos[args.from_prototype].get("rooms", []):
            hits = labels.get(room["name"].upper(), [])
            if len(hits) != 1:
                (ambiguous if hits else unmatched).append(room["name"])
                continue
            data["control_points"].append({
                "name": room["name"], "cad": list(hits[0]), "lonlat": [room["lon"], room["lat"]],
                "source": "prototype", "note": "room label insert point", "use": True})

        print(f"{len(data['control_points'])} control points from prototype '{args.from_prototype}'")
        if unmatched:
            print(f"  not on this floor's labels: {', '.join(unmatched)}")
        if ambiguous:
            print(f"  label appears more than once on the floor, skipped: {', '.join(ambiguous)}")

    save(floor, data)
    print(f"wrote {georef_path(floor)}")


def _fit_points(points, scale=None):
    cad = [p["cad"] for p in points]
    lonlat = [p["lonlat"] for p in points]
    t = fit_similarity(cad, lonlat, scale)
    return t, residuals_m(t, cad, lonlat)


def cmd_fit(args):
    floor = args.floor.upper()
    data = load(floor)
    idx = [i for i, p in enumerate(data["control_points"]) if p.get("use", True)]
    used = [data["control_points"][i] for i in idx]
    if len(used) < 3:
        sys.exit(f"{floor}: {len(used)} control points in use, need at least 3")

    # Set "scale_m_per_unit" in the file (0.0254 for inches) to trust the
    # drawing's scale and fit only rotation and offset; leave it out to fit it.
    scale = data.get("scale_m_per_unit")
    t, res = _fit_points(used, scale)
    t["scale_locked"] = scale is not None
    flagged = set(flag_outliers(res))
    rms = float(np.sqrt(np.mean(res ** 2)))
    scale_err = (t["scale_m_per_unit"] / INCH_M - 1) * 100

    check_results = []
    for c in data.get("checks", []):
        units = float(np.linalg.norm(np.subtract(c["cad_b"], c["cad_a"])))
        cad_m = units * t["scale_m_per_unit"]
        check_results.append({"what": c["what"], "measured_m": c["measured_m"],
                              "plan_m": round(cad_m, 3), "diff_m": round(cad_m - c["measured_m"], 3),
                              "plan_m_at_inches": round(units * INCH_M, 3)})

    order = np.argsort(-res)
    data["fit"] = {
        "transform": t,
        "points_used": len(used),
        "rms_m": round(rms, 3),
        "max_m": round(float(res.max()), 3),
        "scale_vs_inches_pct": round(scale_err, 2),
        # "point" is the index into control_points, since names can repeat
        "residuals": [{"point": idx[i], "name": used[i]["name"], "source": used[i].get("source"),
                       "residual_m": round(float(res[i]), 3), "flagged": bool(i in flagged)}
                      for i in order],
        "check_results": check_results,
    }

    print(f"{floor}: {len(used)} points, RMS {rms:.2f} m, max {res.max():.2f} m")
    print(f"  scale {t['scale_m_per_unit']:.6f} m/unit ({scale_err:+.2f}% vs inches"
          f"{', locked' if scale is not None else ', fitted'}), "
          f"rotation {t['rotation_deg']:.2f} deg")
    print("  worst residuals:")
    for i in order[:args.show]:
        mark = "  <-- FLAGGED" if i in flagged else ""
        print(f"    {used[i]['name']:>10}  {res[i]:6.2f} m  ({used[i].get('source')}){mark}")
    if flagged:
        print(f"  {len(flagged)} flagged point(s): check them, then fix the point or set \"use\": false")
    for c in check_results:
        print(f"  check '{c['what']}': measured {c['measured_m']} m, plan {c['plan_m']} m "
              f"(at inches {c['plan_m_at_inches']} m), diff {c['diff_m']:+} m")

    if args.holdout:
        # Both ways, so the team can see whether locking the scale helps.
        holdout(used, None, "fitted scale")
        holdout(used, scale or INCH_M, "scale locked")

    save(floor, data)
    print(f"wrote fit to {georef_path(floor)}")


def holdout(used, scale, label):
    """Fit on every other point and measure the error on the rest, both ways.
    Unlike the RMS above, these points never influenced the fit, so this is
    the honest accuracy figure for a room the transform hasn't seen."""
    pts = sorted(used, key=lambda p: p["name"])
    errs = []
    for train, test in ((pts[0::2], pts[1::2]), (pts[1::2], pts[0::2])):
        if len(train) < 3 or not test:
            print(f"  holdout ({label}): not enough points")
            return
        t, _ = _fit_points(train, scale)
        errs.extend(residuals_m(t, [p["cad"] for p in test], [p["lonlat"] for p in test]))
    errs = np.array(errs)
    print(f"  holdout, {label} ({len(errs)} points): RMS {np.sqrt(np.mean(errs ** 2)):.2f} m, "
          f"median {np.median(errs):.2f} m, 90th pct {np.percentile(errs, 90):.2f} m")


def _flatten(item, step_deg=10):
    """A shape item from the floor JSON as a list of polylines (CAD units)."""
    op = item["op"]
    if op in ("line", "polyline"):
        pts = list(item["points"])
        if item.get("closed"):
            pts.append(pts[0])
        return [pts]
    if op in ("arc", "circle"):
        (cx, cy), r = item["center"], item["radius"]
        a0, a1 = (item["start_angle"], item["end_angle"]) if op == "arc" else (0, 360)
        if a1 <= a0:
            a1 += 360
        angles = np.radians(np.linspace(a0, a1, max(int((a1 - a0) / step_deg), 2) + 1))
        return [[[cx + r * np.cos(a), cy + r * np.sin(a)] for a in angles]]
    if op == "ellipse":
        (cx, cy), (mx, my), ratio = item["center"], item["major_axis"], item["ratio"]
        angles = np.radians(np.arange(0, 361, step_deg))
        return [[[cx + mx * np.cos(a) - my * ratio * np.sin(a),
                  cy + my * np.cos(a) + mx * ratio * np.sin(a)] for a in angles]]
    return []


def cmd_preview(args):
    floor = args.floor.upper()
    data = load(floor)
    t = data.get("fit", {}).get("transform")
    if not t:
        sys.exit(f"{floor} has no fit yet -- run: python georef.py fit {floor}")
    plan = floor_json(floor)

    def lonlat(pts):
        return [[round(float(lon), 8), round(float(lat), 8)] for lon, lat in apply(t, pts)]

    features = []
    for shape in plan["shapes"]:
        for item in shape["items"]:
            for line in _flatten(item):
                if len(line) >= 2:
                    features.append({"type": "Feature", "properties": {"kind": "shape", "layer": shape["layer"]},
                                     "geometry": {"type": "LineString", "coordinates": lonlat(line)}})
    for tl in plan["text_lines"]:
        features.append({"type": "Feature", "properties": {"kind": "label", "text": tl["text"], "layer": tl["layer"]},
                         "geometry": {"type": "Point", "coordinates": lonlat([[tl["x"], tl["y"]]])[0]}})

    # Where each control point says it belongs (marker-color for geojson.io),
    # so a big residual shows up as a visible gap from its label.
    residual = {r["point"]: r for r in data["fit"].get("residuals", [])}
    for i, p in enumerate(data["control_points"]):
        r = residual.get(i, {})
        features.append({"type": "Feature", "properties": {
            "kind": "control_point", "name": p["name"], "source": p.get("source"), "use": p.get("use", True),
            "residual_m": r.get("residual_m"),
            "marker-color": "#d33" if r.get("flagged") else ("#888" if not p.get("use", True) else "#2a2")},
            "geometry": {"type": "Point", "coordinates": p["lonlat"]}})

    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out = PREVIEW_DIR / f"{floor}.geojson"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    print(f"wrote {out} ({len(features)} features) -- drag it onto https://geojson.io to check it")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="create georef/<floor>.json")
    p.add_argument("floor", help="e.g. AS101-01")
    p.add_argument("--from-prototype", metavar="NAME", help="seed points from a prototype building, e.g. esh")
    p.add_argument("--prototype", default=PROTOTYPE_HTML, help="path to the prototype index.html")
    p.add_argument("--force", action="store_true", help="replace an existing file")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("fit", help="fit the transform and report the error")
    p.add_argument("floor")
    p.add_argument("--holdout", action="store_true", help="also measure error on points left out of the fit")
    p.add_argument("--show", type=int, default=10, help="how many worst residuals to print")
    p.set_defaults(func=cmd_fit)

    p = sub.add_parser("preview", help="write the floor in lon/lat as GeoJSON")
    p.add_argument("floor")
    p.set_defaults(func=cmd_preview)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
