"""
Assign each zone to the official district it sits in, by geometry.

Some cities' boundary sources carried the parent district and some did not.
Where they did not, the answer is still in the map: the district is the
polygon the zone's centre falls inside. The districts come from
OpenStreetMap's administrative relations — the same boundaries the city
publishes — and the test is a plain ray crossing count, which works on the
relation's member ways without having to stitch them into ordered rings first.

Nothing is guessed: a zone whose centre falls in no district is left ungrouped
and reported, rather than attached to the nearest one.

    python3 group_zones_geometric.py roma
"""
import json, os, subprocess, sys, time, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ZONES = os.path.join(HERE, "data_zones")
UA = "WandrozGroups/1.0 (https://www.wandroz.com; hellowandroz@gmail.com)"
EPS = ["https://overpass-api.de/api/interpreter",
       "https://overpass.kumi.systems/api/interpreter"]

# city -> (bounding centre lat, lon, radius m, admin_level, label to expect)
CITIES = {
    "roma":      (41.9028, 12.4964, 22000, 9,  "Municipio"),
    "milano":    (45.4642, 9.1900, 14000, 9,  "Municipio"),
    "firenze":   (43.7696, 11.2558, 10000, 9,  "Quartiere"),
    "amsterdam": (52.3676, 4.9041, 14000, 9,  "Stadsdeel"),
}


def overpass(lat, lon, radius, level):
    q = ('[out:json][timeout:180];'
         'rel["boundary"="administrative"]["admin_level"="%d"](around:%d,%f,%f);'
         'out geom tags;' % (level, radius, lat, lon))
    last = None
    for i, ep in enumerate(EPS * 2):
        res = subprocess.run(["curl", "-sS", "--max-time", "240", "-A", UA,
                              "--data", urllib.parse.urlencode({"data": q}), ep],
                             capture_output=True, text=True)
        if res.returncode == 0:
            try:
                return json.loads(res.stdout)["elements"]
            except Exception as e:
                last = e
        else:
            last = res.stderr[:150]
        time.sleep(8)
    raise RuntimeError("overpass: %s" % last)


def segments(rel):
    """Every boundary segment of the relation, order irrelevant."""
    out = []
    for m in rel.get("members", []):
        if m.get("role") not in ("outer", "inner", ""):
            continue
        g = m.get("geometry") or []
        for a, b in zip(g, g[1:]):
            if a["lat"] != b["lat"] or a["lon"] != b["lon"]:
                out.append((a["lon"], a["lat"], b["lon"], b["lat"]))
    return out


def inside(x, y, segs):
    """Ray crossing count. A closed boundary gives odd parity inside it, and
    that holds whether or not the ways arrive in ring order."""
    n = 0
    for x1, y1, x2, y2 in segs:
        if (y1 > y) != (y2 > y):
            xx = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xx > x:
                n += 1
    return n % 2 == 1


def centroid(coords):
    ring = coords[0]
    return (sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring))


def main(city):
    lat, lon, radius, level, kind = CITIES[city]
    rels = [r for r in overpass(lat, lon, radius, level) if r.get("members")]
    districts = []
    for r in rels:
        name = (r.get("tags") or {}).get("name")
        if not name:
            continue
        districts.append((name, segments(r)))
    print("%s: %d distretti da OpenStreetMap (admin_level %d)" % (city, len(districts), level))

    path = os.path.join(ZONES, "%s.json" % city)
    doc = json.load(open(path, encoding="utf-8"))
    hit, missing = 0, []
    for z in doc["zones"]:
        x, y = centroid(z["coords"])
        found = None
        for name, segs in districts:
            if inside(x, y, segs):
                found = name
                break
        if found:
            z["group"] = found
            hit += 1
        else:
            missing.append(z["name"])
    if hit < len(doc["zones"]) * 0.8:
        print("  troppo pochi assegnati (%d/%d): non scrivo niente" % (hit, len(doc["zones"])))
        return
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    groups = sorted({z.get("group") for z in doc["zones"] if z.get("group")})
    print("  %d/%d zone in %d gruppi: %s" % (hit, len(doc["zones"]), len(groups),
                                             ", ".join(groups[:6])))
    if missing:
        print("  senza gruppo (%d): %s" % (len(missing), ", ".join(missing[:6])))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "roma")
