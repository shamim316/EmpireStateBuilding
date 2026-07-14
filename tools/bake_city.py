#!/usr/bin/env python3
"""Bake raw OSM (Overpass) JSON into a compact local-coordinate city data file.

Inputs (fetched by tools/fetch_osm.sh into RAW_DIR):
  buildings_south.json / buildings_north.json  - all buildings, core midtown bbox
  buildings_far.json                           - tall buildings, extended ring
  coastline.json                               - natural=coastline ways
  water.json                                   - inland water (lakes, reservoir)
  parks.json                                   - parks / green space
  roads.json                                   - street grid

Output:
  data/city_data.js  -> window.CITY_DATA = {...}

Coordinate system: meters, origin at the Empire State Building footprint
centroid. +x = east, +z = south (three.js convention: north is -z).
All coordinates are stored as integer decimeters; polygon points after the
first are delta-encoded.
"""
import json
import math
import os
import sys

from shapely.geometry import LineString, Polygon, MultiPolygon, box, Point
from shapely.ops import unary_union, linemerge, polygonize

RAW_DIR = sys.argv[1] if len(sys.argv) > 1 else "raw"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "city_data.js")

ESB_WAY_ID = 34633854

# Core bbox used for the full-detail building fetch (s, w, n, e)
CORE = (40.725, -74.020, 40.790, -73.950)
# Extended bbox for coastline / far ring
EXT = (40.66, -74.07, 40.85, -73.88)

def load(name):
    with open(os.path.join(RAW_DIR, name)) as f:
        return json.load(f)["elements"]

# ---------------------------------------------------------------- projection
M_PER_DEG_LAT = 111132.0

class Proj:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.mlon = 111320.0 * math.cos(math.radians(lat0))
    def xy(self, lat, lon):
        return ((lon - self.lon0) * self.mlon, -(lat - self.lat0) * M_PER_DEG_LAT)

def ring_from_geom(geom, proj):
    return [proj.xy(g["lat"], g["lon"]) for g in geom if g]

def way_polygon(el, proj):
    if "geometry" not in el:
        return None
    pts = ring_from_geom(el["geometry"], proj)
    if len(pts) < 4:
        return None
    try:
        p = Polygon(pts)
        if not p.is_valid:
            p = p.buffer(0)
        return p if not p.is_empty else None
    except Exception:
        return None

def relation_polygon(el, proj):
    outers = []
    for m in el.get("members", []):
        if m.get("role") not in ("outer", "") or "geometry" not in m:
            continue
        pts = ring_from_geom(m["geometry"], proj)
        if len(pts) >= 2:
            outers.append(LineString(pts))
    if not outers:
        return None
    try:
        merged = linemerge(unary_union(outers))
        lines = [merged] if merged.geom_type == "LineString" else list(merged.geoms)
        polys = []
        for ln in lines:
            c = list(ln.coords)
            if len(c) >= 4:
                # force-close (clipped rings)
                if c[0] != c[-1]:
                    c.append(c[0])
                p = Polygon(c)
                if not p.is_valid:
                    p = p.buffer(0)
                if not p.is_empty:
                    polys.append(p)
        if not polys:
            return None
        u = unary_union(polys)
        return u if not u.is_empty else None
    except Exception:
        return None

# ------------------------------------------------------------------- heights
def parse_len(v):
    """Parse an OSM length tag into meters."""
    if v is None:
        return None
    v = v.strip().replace(",", ".")
    try:
        if v.endswith("m"):
            return float(v[:-1].strip())
        if v.endswith("ft") or v.endswith("'"):
            return float(v.rstrip("'tf ").strip()) * 0.3048
        return float(v)
    except ValueError:
        return None

def building_height(tags, oid):
    h = parse_len(tags.get("height")) or parse_len(tags.get("building:height"))
    if h:
        return h
    try:
        lv = float(tags.get("building:levels", ""))
        return lv * 3.3 + 2.5
    except ValueError:
        pass
    return 12.0 + (oid % 17)  # deterministic filler for untagged rowhouses

# ------------------------------------------------------------------ encoding
def enc_ring(coords, q=0.1):
    """Quantize to decimeters, delta-encode after the first point."""
    out = []
    px = pz = 0
    for i, (x, z) in enumerate(coords):
        xi, zi = round(x / q), round(z / q)
        if i == 0:
            out += [xi, zi]
        else:
            if xi == px and zi == pz:
                continue
            out += [xi - px, zi - pz]
        px, pz = xi, zi
    return out

def poly_outer(p, tol, max_pts=80):
    p = p.simplify(tol, preserve_topology=True)
    if p.is_empty:
        return None
    if p.geom_type == "MultiPolygon":
        p = max(p.geoms, key=lambda g: g.area)
    c = list(p.exterior.coords)[:-1]
    if len(c) > max_pts:
        p = p.simplify(tol * 3, preserve_topology=True)
        if p.geom_type == "MultiPolygon":
            p = max(p.geoms, key=lambda g: g.area)
        c = list(p.exterior.coords)[:-1]
        c = c[:max_pts]
    return c if len(c) >= 3 else None

def each_poly(g):
    if g is None or g.is_empty:
        return
    if g.geom_type == "Polygon":
        yield g
    elif g.geom_type in ("MultiPolygon", "GeometryCollection"):
        for s in g.geoms:
            yield from each_poly(s)

# ============================================================ main pipeline
def main():
    b_els = load("buildings_south.json") + load("buildings_north.json")

    # -- origin: ESB centroid
    esb_el = next(e for e in b_els if e["type"] == "way" and e["id"] == ESB_WAY_ID)
    lat0 = sum(g["lat"] for g in esb_el["geometry"]) / len(esb_el["geometry"])
    lon0 = sum(g["lon"] for g in esb_el["geometry"]) / len(esb_el["geometry"])
    proj = Proj(lat0, lon0)
    esb_poly = way_polygon(esb_el, proj)
    print(f"origin lat/lon: {lat0:.7f} {lon0:.7f}  esb area {esb_poly.area:.0f} m2")
    esb_zone = esb_poly.buffer(2)

    # -- core buildings
    buildings, seen = [], set()
    for e in b_els:
        oid = (e["type"], e["id"])
        if oid in seen or e["id"] == ESB_WAY_ID and e["type"] == "way":
            continue
        seen.add(oid)
        tags = e.get("tags", {})
        g = way_polygon(e, proj) if e["type"] == "way" else relation_polygon(e, proj)
        for p in each_poly(g):
            if p.area < 15:
                continue
            if p.intersects(esb_zone):
                continue
            c = poly_outer(p, 0.7)
            if not c:
                continue
            h = building_height(tags, e["id"])
            buildings.append([round(h * 10), enc_ring(c)])
    print("core buildings:", len(buildings))

    # -- far ring (tall only, outside core bbox)
    sw = proj.xy(CORE[0], CORE[1])
    ne = proj.xy(CORE[2], CORE[3])
    cb = box(min(sw[0], ne[0]), min(sw[1], ne[1]), max(sw[0], ne[0]), max(sw[1], ne[1]))
    far = []
    for e in load("buildings_far.json"):
        oid = (e["type"], e["id"])
        if oid in seen:
            continue
        tags = e.get("tags", {})
        g = way_polygon(e, proj) if e["type"] == "way" else relation_polygon(e, proj)
        for p in each_poly(g):
            if p.area < 40 or cb.contains(p.centroid):
                continue
            c = poly_outer(p, 1.5)
            if not c:
                continue
            h = building_height(tags, e["id"])
            far.append([round(h * 10), enc_ring(c)])
    print("far buildings:", len(far))

    # -- land from coastline
    ext_pts = [proj.xy(EXT[0], EXT[1]), proj.xy(EXT[2], EXT[3])]
    ext_box = box(min(p[0] for p in ext_pts), min(p[1] for p in ext_pts),
                  max(p[0] for p in ext_pts), max(p[1] for p in ext_pts))
    lines = []
    for e in load("coastline.json"):
        if "geometry" in e:
            pts = ring_from_geom(e["geometry"], proj)
            if len(pts) >= 2:
                lines.append(LineString(pts))
    clipped = unary_union(lines).intersection(ext_box)
    faces = list(polygonize(unary_union([clipped, ext_box.boundary])))
    land_tests = [(40.7484, -73.9857), (40.745, -74.035), (40.72, -74.04),
                  (40.77, -74.02), (40.80, -74.00), (40.70, -73.955),
                  (40.712, -73.955), (40.728, -73.95), (40.745, -73.94),
                  (40.77, -73.92), (40.7615, -73.9500), (40.793, -73.9219),
                  (40.6895, -74.0158), (40.68, -74.00)]
    test_pts = [Point(*proj.xy(a, b)) for a, b in land_tests]
    land = []
    for f in faces:
        if any(f.contains(tp) for tp in test_pts):
            c = poly_outer(f, 4.0, max_pts=1200)
            if c:
                land.append(enc_ring(c, q=0.5))
    print("land polys:", len(land), " faces total:", len(faces))

    # -- inland water (lakes, ponds, reservoir)
    water = []
    for e in load("water.json"):
        g = way_polygon(e, proj) if e["type"] == "way" else relation_polygon(e, proj)
        for p in each_poly(g):
            if p.area < 3000:
                continue
            c = poly_outer(p, 2.0, max_pts=300)
            if c:
                water.append(enc_ring(c, q=0.5))
    print("inland water polys:", len(water))

    # -- parks (dissolved)
    park_polys = []
    for e in load("parks.json"):
        g = way_polygon(e, proj) if e["type"] == "way" else relation_polygon(e, proj)
        for p in each_poly(g):
            if p.area >= 400:
                park_polys.append(p)
    dissolved = unary_union(park_polys)
    parks = []
    for p in each_poly(dissolved):
        if p.area < 1200:
            continue
        c = poly_outer(p, 2.0, max_pts=600)
        if c:
            parks.append(enc_ring(c, q=0.5))
    print("park polys:", len(parks))

    # -- roads
    widths = {"motorway": 20, "trunk": 18, "primary": 18, "secondary": 15,
              "tertiary": 12, "residential": 9, "unclassified": 9}
    roads = []
    for e in load("roads.json"):
        tags = e.get("tags", {})
        if tags.get("tunnel") in ("yes", "building_passage") or "geometry" not in e:
            continue
        pts = ring_from_geom(e["geometry"], proj)
        if len(pts) < 2:
            continue
        ln = LineString(pts).simplify(1.0)
        w = widths.get(tags.get("highway"), 9)
        roads.append([w, enc_ring(list(ln.coords), q=0.5)])
    print("roads:", len(roads))

    esb_ring = enc_ring(list(esb_poly.exterior.coords)[:-1])

    data = {
        "origin": [round(lat0, 7), round(lon0, 7)],
        "esb": esb_ring,
        "buildings": buildings,
        "far": far,
        "land": land,
        "water": water,
        "parks": parks,
        "roads": roads,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    js = "window.CITY_DATA=" + json.dumps(data, separators=(",", ":")) + ";\n"
    with open(OUT, "w") as f:
        f.write(js)
    print(f"wrote {OUT}: {len(js)/1e6:.2f} MB")

if __name__ == "__main__":
    main()
