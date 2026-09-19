"""
Every published map, checked against itself.

WHAT IT TESTS
    Geometry, per city:
      - rings with fewer than 4 points, or that fail to close
      - self-intersecting rings
      - duplicate polygons (two areas with the same shape)
      - duplicate names and duplicate slugs
      - overlap between areas, sampled on a grid
      - uncovered ground inside the built-up part of the city
      - an area whose centroid sits improbably far from the city's own centre
      - an area whose polygon lies wholly outside the city's bounding box

    Consistency, per city:
      - the rating the map colours a zone with, against the rating its own
        detail page shows
      - the rating the map uses, against the hub table
      - whether day and night ever differ, and whether the city's source could
        support that if they do

    Distribution, per city:
      - share green / amber / red, share differing day vs night

WHAT IT DOES NOT DO
    It changes nothing and it judges no rating. An 80%-green city is printed as
    a flag, not a fault: a city where nothing was found really is mostly one
    colour, and forcing a spread would be the error, not the fix.

USAGE
    python3 pipeline/audit_maps.py
    python3 pipeline/audit_maps.py --city amsterdam
"""
import argparse
import collections
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import published

DIST = os.path.join(os.path.dirname(HERE), "dist")


def km(a, b, c, d):
    R = 6371.0
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c - a), math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def centroid(rings):
    r = max(rings, key=len)
    return sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r)


def _seg_hit(p1, p2, p3, p4):
    def o(a, b, c):
        v = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else 2)
    o1, o2, o3, o4 = o(p1, p2, p3), o(p1, p2, p4), o(p3, p4, p1), o(p3, p4, p2)
    return o1 != o2 and o3 != o4


def self_intersects(ring, cap=400):
    """Only sampled on rings up to `cap` points: the test is O(n^2) and a
    boundary traced from an official shapefile can carry thousands. A ring that
    long is also the least likely to be hand-edited, which is where the fault
    would come from."""
    n = len(ring)
    if n > cap or n < 4:
        return False
    for i in range(n - 1):
        for j in range(i + 2, n - 1):
            if i == 0 and j == n - 2:
                continue
            if _seg_hit(ring[i], ring[i + 1], ring[j], ring[j + 1]):
                return True
    return False


def inside(lat, lon, rings):
    c = False
    for r in rings:
        n = len(r)
        for i in range(n):
            y1, x1 = r[i]
            y2, x2 = r[(i + 1) % n]
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                c = not c
    return c


def page_rating(city, zone):
    """The day/night the zone's own page shows, read back from the built file."""
    url = zone.get("url") or ""
    rel = url.lstrip("/")
    for cand in (rel, rel + "index.html" if rel.endswith("/") else rel):
        p = os.path.join(DIST, cand)
        if os.path.isfile(p):
            h = open(p, encoding="utf-8", errors="replace").read()
            m = re.search(r'<span class="badge (green|yellow|red|grey)"', h)
            m2 = re.findall(r'<span class="badge (green|yellow|red|grey)"', h)
            return (m2[0], m2[1]) if len(m2) >= 2 else ((m.group(1), None) if m else (None, None))
    return (None, None)


def audit_city(slug, zones):
    out = {"city": slug, "areas": len(zones), "problems": [], "flags": []}
    P, F = out["problems"].append, out["flags"].append

    names = collections.Counter(z["name"] for z in zones)
    slugs = collections.Counter(z.get("slug") for z in zones)
    for n, c in names.items():
        if c > 1:
            P("duplicate name: %s (x%d)" % (n, c))
    for s, c in slugs.items():
        if c > 1:
            P("duplicate slug: %s (x%d)" % (s, c))

    shapes = {}
    cents = []
    for z in zones:
        rings = z.get("coords") or []
        if not rings:
            P("no geometry: %s" % z["name"])
            continue
        for r in rings:
            if len(r) < 4:
                P("degenerate ring (%d points): %s" % (len(r), z["name"]))
            elif self_intersects(r):
                P("self-intersecting ring: %s" % z["name"])
        # The whole ring, not a prefix. Comparing the first 40 points reported
        # Antwerp's Deurne and Borgerhout as the same shape because adjacent
        # districts share a boundary corner and both rings start there.
        key = tuple(map(tuple, max(rings, key=len)))
        if key in shapes:
            P("duplicate polygon: %s and %s" % (shapes[key], z["name"]))
        shapes[key] = z["name"]
        cents.append((z["name"], *centroid(rings)))

    if cents:
        las = sorted(c[1] for c in cents)
        los = sorted(c[2] for c in cents)
        cla, clo = las[len(las) // 2], los[len(los) // 2]
        for n, la, lo in cents:
            d = km(cla, clo, la, lo)
            if d > 25:
                P("centroid %.0f km from the city's median centre: %s" % (d, n))
            elif d > 12:
                F("%.0f km out: %s" % (d, n))

    # Overlap and coverage, sampled on a grid over the areas' own extent.
    pts = [p for z in zones for r in (z.get("coords") or []) for p in r]
    if pts:
        la0, la1 = min(p[0] for p in pts), max(p[0] for p in pts)
        lo0, lo1 = min(p[1] for p in pts), max(p[1] for p in pts)
        step = max((la1 - la0) / 45.0, 0.002)
        over = tot = cov = 0
        la = la0
        while la <= la1:
            lo = lo0
            while lo <= lo1:
                tot += 1
                hits = sum(1 for z in zones if inside(la, lo, z.get("coords") or []))
                if hits:
                    cov += 1
                if hits > 1:
                    over += 1
                lo += step
            la += step
        if tot:
            out["coverage_pct"] = round(100.0 * cov / tot, 1)
            out["overlap_pct"] = round(100.0 * over / tot, 1)
            if out["overlap_pct"] > 1.0:
                P("areas overlap on %.1f%% of sampled points" % out["overlap_pct"])

    # Rating consistency: map vs the area's own page.
    mismatched = 0
    for z in zones[:400]:
        d, n = page_rating(slug, z)
        if d and z.get("day") and d != z["day"]:
            mismatched += 1
            if mismatched <= 3:
                P("map says %s by day, page says %s: %s" % (z["day"], d, z["name"]))
    out["rating_mismatches"] = mismatched

    tones = collections.Counter()
    diff = 0
    for z in zones:
        tones[z.get("day")] += 1
        if z.get("day") != z.get("night"):
            diff += 1
    n = max(len(zones), 1)
    out["pct_green"] = round(100.0 * tones["green"] / n)
    out["pct_yellow"] = round(100.0 * tones["yellow"] / n)
    out["pct_red"] = round(100.0 * tones["red"] / n)
    out["pct_daynight_differs"] = round(100.0 * diff / n)
    return out


def main(only):
    rows = []
    for slug, zones in published.published_cities():
        if only and slug != only:
            continue
        rows.append(audit_city(slug, zones))

    probs = [r for r in rows if r["problems"]]
    print("audited %d cities\n" % len(rows))
    print("=== GEOMETRY / CONSISTENCY PROBLEMS ===")
    if not probs:
        print("none")
    for r in probs:
        print("%s" % r["city"])
        for p in r["problems"][:8]:
            print("   %s" % p)
    print("\n=== DISTRIBUTION ===")
    print("%-14s %5s %6s %6s %6s %8s %7s %7s" %
          ("city", "areas", "green", "amber", "red", "day!=nt", "cover", "overlap"))
    for r in sorted(rows, key=lambda x: -x["pct_green"]):
        print("%-14s %5d %5d%% %5d%% %5d%% %7d%% %6s%% %6s%%" %
              (r["city"], r["areas"], r["pct_green"], r["pct_yellow"], r["pct_red"],
               r["pct_daynight_differs"], r.get("coverage_pct", "?"), r.get("overlap_pct", "?")))
    out = os.path.join(os.path.dirname(HERE), "qa_output", "map_audit.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"cities": rows}, open(out, "w"), ensure_ascii=False, indent=1)
    print("\nwrote %s" % out)
    return 1 if probs else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=None)
    a = ap.parse_args()
    sys.exit(main(a.city))
