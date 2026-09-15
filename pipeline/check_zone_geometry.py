"""
Does a city's set of zone polygons actually tile the city?

WHY THIS EXISTS
    The first check on the Italian boundaries was "does the main square fall
    inside some zone". Genoa passed it and was still wrong: its Medio Ponente
    polygon had three rings and reached 6 km up the Polcevera valley where it
    has no business being, and Centro Est had a gap along the waterfront that
    swallowed via Prè and the Porto Antico — the two places in Genoa a visitor
    is most likely to stand. One point cannot see either fault.

    So this samples a grid across the city and asks two questions a correct
    subdivision must answer the same way everywhere: is this point in exactly
    one zone, and is it in any zone at all. Holes show up as uncovered land
    inside the built-up area; a mis-stitched ring shows up as overlap, because
    administrative areas do not overlap.

    Coverage is never 100%: the grid is a rectangle and a city is not, so sea,
    neighbouring comuni and mountain fall outside legitimately. What matters is
    that the covered fraction is high and that overlap is essentially zero.

    python3 check_zone_geometry.py genova [--step 0.004]
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def inside(lat, lon, rings):
    n = 0
    for r in rings:
        for (y1, x1), (y2, x2) in zip(r, r[1:] + r[:1]):
            if (y1 > lat) != (y2 > lat):
                if x1 + (lat - y1) * (x2 - x1) / (y2 - y1) > lon:
                    n += 1
    return n % 2 == 1


def load(key):
    for name in ("%s_boundaries.json" % key, "%s.json" % key):
        p = os.path.join(HERE, "data_zones", name)
        if os.path.exists(p):
            return json.load(open(p, encoding="utf-8")), name
    raise SystemExit("no zone file for %s" % key)


def main(key, step=0.004):
    doc, name = load(key)
    zones = doc["zones"]
    pts = [p for z in zones for r in z["coords"] for p in r]
    la0, la1 = min(p[0] for p in pts), max(p[0] for p in pts)
    lo0, lo1 = min(p[1] for p in pts), max(p[1] for p in pts)

    total = covered = overlapping = 0
    per_zone = {z["name"]: 0 for z in zones}
    overlaps = {}
    lat = la0
    while lat <= la1:
        lon = lo0
        while lon <= lo1:
            total += 1
            hit = [z["name"] for z in zones if inside(lat, lon, z["coords"])]
            if hit:
                covered += 1
                per_zone[hit[0]] += 1
            if len(hit) > 1:
                overlapping += 1
                overlaps[" + ".join(sorted(hit))] = overlaps.get(" + ".join(sorted(hit)), 0) + 1
            lon += step
        lat += step

    print("%s (%s): %d zones, grid %d points at %.3f deg" % (key, name, len(zones), total, step))
    print("  covered   %5.1f%%   (%d of %d)" % (100.0 * covered / total, covered, total))
    print("  overlap   %5.2f%%   (%d points in more than one zone)" % (100.0 * overlapping / total, overlapping))
    for pair, n in sorted(overlaps.items(), key=lambda kv: -kv[1])[:5]:
        print("      %-44s %d pts" % (pair, n))
    empty = [n for n, c in per_zone.items() if c == 0]
    if empty:
        print("  zones the grid never landed in: %s" % ", ".join(empty))
    rings = {z["name"]: len(z["coords"]) for z in zones if len(z["coords"]) > 1}
    if rings:
        print("  multi-ring zones (worth eyeballing): %s"
              % ", ".join("%s=%d" % (k, v) for k, v in rings.items()))
    # A subdivision of one comune should not overlap itself at all, and should
    # cover most of its own bounding box's land. These are the two numbers to
    # read; the thresholds are deliberately loose because the grid is a
    # rectangle over a coastline.
    verdict = "OK" if overlapping == 0 else "SUSPECT — administrative areas do not overlap"
    print("  verdict: %s" % verdict)
    return overlapping


if __name__ == "__main__":
    step = 0.004
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--step" in sys.argv:
        step = float(sys.argv[sys.argv.index("--step") + 1])
    for k in args:
        main(k, step)
        print()
